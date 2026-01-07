#!/usr/bin/env python3
"""
Storage Audit Script

Audits MongoDB collections and Pinecone namespaces to identify inconsistencies,
provide usage statistics, and help with migration planning.

Usage:
    python scripts/audit_storage.py
    python scripts/audit_storage.py --json
    python scripts/audit_storage.py --dangerously-print
    python scripts/audit_storage.py --format table --output report.json
"""

import os
import sys
import json
import argparse
from collections import defaultdict
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


class StorageAuditor:
    """Audits MongoDB and Pinecone storage"""
    
    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        pinecone_api_key: Optional[str] = None,
        pinecone_index: Optional[str] = None,
        redact_sensitive: bool = True
    ):
        self.mongo_uri = mongo_uri or Config.MONGO_URI
        self.pinecone_api_key = pinecone_api_key or Config.PINECONE_API_KEY
        self.pinecone_index = pinecone_index or Config.PINECONE_INDEX_NAME
        self.redact_sensitive = redact_sensitive
        
    def redact(self, text: str) -> str:
        """Redact sensitive information if needed"""
        if not self.redact_sensitive or not text:
            return text
        
        # Redact emails
        if "@" in text:
            parts = text.split("@")
            if len(parts) == 2:
                return f"{parts[0][:2]}***@{parts[1]}"
        
        # Redact short identifiers (likely usernames)
        if len(text) <= 10 and not "@" in text:
            return f"{text[:2]}***"
        
        return text
    
    def audit_mongodb(self) -> Dict[str, Any]:
        """Audit MongoDB collections"""
        result = {
            "status": "error",
            "database": None,
            "collections": [],
            "total_documents": 0,
            "errors": []
        }
        
        if not self.mongo_uri:
            result["errors"].append("MONGO_URI not configured")
            return result
        
        try:
            db_manager = DatabaseManager()
            if not db_manager.connect():
                result["errors"].append("Failed to connect to MongoDB")
                return result
            
            db = db_manager.db
            if db is None:
                result["errors"].append("Database not initialized")
                return result
            
            result["database"] = db.name if not self.redact_sensitive else self.redact(db.name)
            result["mongo_uri"] = self.mongo_uri if not self.redact_sensitive else "***REDACTED***"
            
            collections = db.list_collection_names()
            
            for collection_name in sorted(collections):
                collection = db[collection_name]
                count = collection.count_documents({})
                
                # Get sample document for structure
                sample = collection.find_one({}) if count > 0 else None
                fields = list(sample.keys()) if sample else []
                
                result["collections"].append({
                    "name": collection_name,
                    "document_count": count,
                    "fields": fields,
                    "has_user_id": "user_id" in fields,
                    "has_email": any("email" in f.lower() for f in fields)
                })
                
                result["total_documents"] += count
            
            result["status"] = "success"
            db_manager.disconnect()
            
        except Exception as e:
            result["errors"].append(str(e))
        
        return result
    
    def audit_pinecone(self) -> Dict[str, Any]:
        """Audit Pinecone index and namespaces"""
        result = {
            "status": "error",
            "index_name": self.pinecone_index,
            "namespaces": [],
            "total_vectors": 0,
            "namespace_analysis": {},
            "errors": []
        }
        
        if not self.pinecone_api_key:
            result["errors"].append("PINECONE_API_KEY not configured")
            return result
        
        try:
            from pinecone import Pinecone
            
            pc = Pinecone(api_key=self.pinecone_api_key)
            
            # Check if index exists
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            
            if self.pinecone_index not in existing_indexes:
                result["errors"].append(f"Index '{self.pinecone_index}' does not exist")
                result["available_indexes"] = existing_indexes
                return result
            
            # Get index stats
            index = pc.Index(self.pinecone_index)
            stats = index.describe_index_stats()
            
            result["dimension"] = stats.dimension
            result["index_fullness"] = stats.index_fullness
            result["total_vectors"] = stats.total_vector_count
            
            namespaces = stats.namespaces
            
            for namespace_name, namespace_stats in sorted(namespaces.items(), key=lambda x: x[1].get("vector_count", 0), reverse=True):
                vector_count = namespace_stats.get("vector_count", 0)
                
                result["namespaces"].append({
                    "namespace": self.redact(namespace_name),
                    "vector_count": vector_count,
                    "namespace_type": self._classify_namespace(namespace_name)
                })
            
            # Namespace analysis
            result["namespace_analysis"] = self._analyze_namespaces(namespaces)
            
            result["status"] = "success"
            
        except Exception as e:
            result["errors"].append(str(e))
        
        return result
    
    def _classify_namespace(self, namespace: str) -> str:
        """Classify namespace type"""
        if "@" in namespace:
            return "email"
        elif len(namespace) <= 10 and namespace.isalnum():
            return "username"
        elif namespace.startswith("u:"):
            return "canonical_user_id"
        elif namespace.startswith("anon-"):
            return "anonymous"
        elif namespace.startswith("test-"):
            return "test"
        else:
            return "unknown"
    
    def _analyze_namespaces(self, namespaces: Dict) -> Dict[str, Any]:
        """Analyze namespace patterns and identify potential duplicates"""
        analysis = {
            "by_type": defaultdict(int),
            "total_count": len(namespaces),
            "potential_duplicates": []
        }
        
        # Group by type
        for namespace_name in namespaces.keys():
            ns_type = self._classify_namespace(namespace_name)
            analysis["by_type"][ns_type] += 1
        
        # Find potential duplicates (similar namespaces)
        namespace_list = list(namespaces.keys())
        checked = set()
        
        for i, ns1 in enumerate(namespace_list):
            if ns1 in checked:
                continue
            
            similar_group = [ns1]
            
            for ns2 in namespace_list[i+1:]:
                if ns2 in checked:
                    continue
                
                # Check if they might be the same user
                # e.g., "v" and "vane" and "vanesa" and "vanesa.taneva@gmail.com"
                if self._might_be_same_user(ns1, ns2):
                    similar_group.append(ns2)
                    checked.add(ns2)
            
            if len(similar_group) > 1:
                total_vectors = sum(namespaces[ns].get("vector_count", 0) for ns in similar_group)
                analysis["potential_duplicates"].append({
                    "namespaces": [self.redact(ns) for ns in similar_group] if self.redact_sensitive else similar_group,
                    "count": len(similar_group),
                    "total_vectors": total_vectors
                })
            
            checked.add(ns1)
        
        return analysis
    
    def _might_be_same_user(self, ns1: str, ns2: str) -> bool:
        """Check if two namespaces might belong to the same user"""
        # Skip anonymous and test users
        if any(ns.startswith(("anon-", "test-")) for ns in [ns1, ns2]):
            return False
        
        # Check if one is a substring of the other (case insensitive)
        ns1_lower = ns1.lower()
        ns2_lower = ns2.lower()
        
        # "v" in "vane" or "vane" in "vanesa"
        if ns1_lower in ns2_lower or ns2_lower in ns1_lower:
            return True
        
        # Check if email prefix matches username
        # e.g., "vanesa" and "vanesa.taneva@gmail.com"
        if "@" in ns1 or "@" in ns2:
            email_ns = ns1 if "@" in ns1 else ns2
            other_ns = ns2 if "@" in ns1 else ns1
            
            email_prefix = email_ns.split("@")[0].lower()
            if other_ns.lower() in email_prefix or email_prefix.startswith(other_ns.lower()):
                return True
        
        return False
    
    def generate_report(self, output_format: str = "text") -> str:
        """Generate audit report"""
        mongo_audit = self.audit_mongodb()
        pinecone_audit = self.audit_pinecone()
        
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "mongodb": mongo_audit,
            "pinecone": pinecone_audit,
            "recommendations": self._generate_recommendations(mongo_audit, pinecone_audit)
        }
        
        if output_format == "json":
            return json.dumps(report, indent=2)
        elif output_format == "table":
            return self._format_table_report(report)
        else:
            return self._format_text_report(report)
    
    def _generate_recommendations(self, mongo_audit: Dict, pinecone_audit: Dict) -> List[str]:
        """Generate recommendations based on audit results"""
        recommendations = []
        
        # Check for namespace inconsistencies
        if pinecone_audit["status"] == "success":
            ns_analysis = pinecone_audit.get("namespace_analysis", {})
            
            if ns_analysis.get("potential_duplicates"):
                recommendations.append({
                    "priority": "HIGH",
                    "issue": "Potential duplicate namespaces detected",
                    "count": len(ns_analysis["potential_duplicates"]),
                    "action": "Run namespace migration script to consolidate user vectors",
                    "script": "scripts/migrate_pinecone_namespaces.py"
                })
            
            by_type = ns_analysis.get("by_type", {})
            if by_type.get("username", 0) > 0 or by_type.get("email", 0) > 0:
                recommendations.append({
                    "priority": "HIGH",
                    "issue": "Non-canonical namespace formats detected",
                    "details": f"Found {by_type.get('username', 0)} username-based and {by_type.get('email', 0)} email-based namespaces",
                    "action": "Migrate to canonical format (u:<userId>)",
                    "script": "scripts/migrate_pinecone_namespaces.py"
                })
        
        # Check MongoDB structure
        if mongo_audit["status"] == "success":
            collections = {c["name"]: c for c in mongo_audit["collections"]}
            
            # Check for missing collections
            missing = []
            if "preferences" not in collections:
                missing.append("preferences")
            if "projects" not in collections:
                missing.append("projects")
            if "tasks" not in collections:
                missing.append("tasks (consolidated)")
            
            if missing:
                recommendations.append({
                    "priority": "MEDIUM",
                    "issue": "Missing recommended collections",
                    "collections": missing,
                    "action": "Create missing collections for complete memory architecture"
                })
            
            # Check for user_id standardization
            user_id_collections = [c["name"] for c in mongo_audit["collections"] if c.get("has_user_id")]
            if user_id_collections:
                recommendations.append({
                    "priority": "LOW",
                    "issue": "Verify user_id consistency across collections",
                    "collections": user_id_collections,
                    "action": "Ensure all collections use same user identifier format"
                })
        
        return recommendations
    
    def _format_text_report(self, report: Dict) -> str:
        """Format report as plain text"""
        lines = []
        lines.append("=" * 70)
        lines.append("STORAGE AUDIT REPORT")
        lines.append("=" * 70)
        lines.append(f"Generated: {report['generated_at']}")
        lines.append("")
        
        # MongoDB section
        mongo = report["mongodb"]
        lines.append("=" * 70)
        lines.append("MONGODB AUDIT")
        lines.append("=" * 70)
        
        if mongo["status"] == "success":
            lines.append(f"Database: {mongo['database']}")
            lines.append(f"Total Documents: {mongo['total_documents']:,}")
            lines.append(f"Collections: {len(mongo['collections'])}")
            lines.append("")
            lines.append("Collections:")
            
            for col in mongo["collections"]:
                lines.append(f"  - {col['name']}: {col['document_count']:,} documents")
        else:
            lines.append("[ERROR] MongoDB audit failed")
            for error in mongo.get("errors", []):
                lines.append(f"  - {error}")
        
        lines.append("")
        
        # Pinecone section
        pinecone = report["pinecone"]
        lines.append("=" * 70)
        lines.append("PINECONE AUDIT")
        lines.append("=" * 70)
        
        if pinecone["status"] == "success":
            lines.append(f"Index: {pinecone['index_name']}")
            lines.append(f"Total Vectors: {pinecone['total_vectors']:,}")
            lines.append(f"Dimension: {pinecone['dimension']}")
            lines.append(f"Namespaces: {len(pinecone['namespaces'])}")
            lines.append("")
            
            # Namespace analysis
            ns_analysis = pinecone.get("namespace_analysis", {})
            by_type = ns_analysis.get("by_type", {})
            
            if by_type:
                lines.append("Namespace Types:")
                for ns_type, count in sorted(by_type.items()):
                    lines.append(f"  - {ns_type}: {count}")
                lines.append("")
            
            # Top namespaces
            lines.append("Top Namespaces (by vector count):")
            for ns in pinecone["namespaces"][:10]:
                lines.append(f"  - {ns['namespace']}: {ns['vector_count']:,} vectors ({ns['namespace_type']})")
            
            # Potential duplicates
            duplicates = ns_analysis.get("potential_duplicates", [])
            if duplicates:
                lines.append("")
                lines.append(f"[WARNING] Found {len(duplicates)} potential duplicate groups:")
                for dup in duplicates[:5]:
                    lines.append(f"  - {', '.join(dup['namespaces'])}: {dup['total_vectors']} total vectors")
        else:
            lines.append("[ERROR] Pinecone audit failed")
            for error in pinecone.get("errors", []):
                lines.append(f"  - {error}")
        
        lines.append("")
        
        # Recommendations
        recommendations = report.get("recommendations", [])
        if recommendations:
            lines.append("=" * 70)
            lines.append("RECOMMENDATIONS")
            lines.append("=" * 70)
            
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"\n{i}. [{rec['priority']}] {rec['issue']}")
                if "count" in rec:
                    lines.append(f"   Count: {rec['count']}")
                if "details" in rec:
                    lines.append(f"   Details: {rec['details']}")
                if "collections" in rec:
                    lines.append(f"   Collections: {', '.join(rec['collections'])}")
                lines.append(f"   Action: {rec['action']}")
                if "script" in rec:
                    lines.append(f"   Script: {rec['script']}")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def _format_table_report(self, report: Dict) -> str:
        """Format report as ASCII table"""
        # Similar to text but with better formatting
        return self._format_text_report(report)


def main():
    parser = argparse.ArgumentParser(description="Audit MongoDB and Pinecone storage")
    parser.add_argument("--format", choices=["text", "json", "table"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--dangerously-print", action="store_true",
                        help="Print sensitive information without redaction")
    parser.add_argument("--mongo-uri", help="MongoDB URI (overrides env)")
    parser.add_argument("--pinecone-key", help="Pinecone API key (overrides env)")
    parser.add_argument("--pinecone-index", help="Pinecone index name (overrides env)")
    
    args = parser.parse_args()
    
    # Create auditor
    auditor = StorageAuditor(
        mongo_uri=args.mongo_uri,
        pinecone_api_key=args.pinecone_key,
        pinecone_index=args.pinecone_index,
        redact_sensitive=not args.dangerously_print
    )
    
    # Generate report
    report = auditor.generate_report(output_format=args.format)
    
    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

