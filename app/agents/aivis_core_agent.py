"""
Aivis Core Agent - handles general productivity and chat tasks.

This agent is responsible for:
- General conversation and chat
- Task planning and organization
- Text rewriting and summarization
- Memory management and context retrieval
- Non-domain-specific requests
"""

from typing import List, Dict, Any, Optional


# System prompt for Aivis
AIVIS_SYSTEM_PROMPT = """
You are Aivis, a calm, practical, productivity-oriented AI assistant.
Your primary focus is to help the user manage email, calendar, tasks, projects,
and information overload so they feel more organized, clear, and in control of
their work and life logistics.

Core capabilities:
- Help rewrite, summarize, and draft emails, messages, and documents.
- Help plan and prioritize tasks and projects with clear next steps.
- Help organize information into simple structures (lists, bullets, outlines).

Tone and style:
- Calm, supportive, and grounded. No hype.
- Concise but not cold; a bit warm and human.
- Prefer structured answers (bullets, steps, short sections) for planning and organization.
- Ask clarifying questions only when absolutely necessary to move forward.
- When rewriting text, keep the user's intent and meaning, but improve clarity, tone, and structure.
""".strip()


class AivisCoreAgent:
    """
    General-purpose agent for productivity and chat tasks.
    
    Handles the core chat loop:
    1. Retrieve context from memory
    2. Build messages with system prompt and history
    3. Generate response using LLM
    4. Store conversation in memory
    """
    
    def __init__(
        self,
        llm_service,
        memory_service,
        nodes_service=None,
        use_rag: bool = False,
    ):
        """
        Initialize the Aivis Core agent.
        
        Parameters
        ----------
        llm_service : LLMService
            Service for LLM operations
        memory_service : MemoryService
            Service for memory and conversation storage
        nodes_service : NodesService, optional
            Service for knowledge graph (future)
        use_rag : bool
            Whether to use RAG for document search - currently not actively used
        """
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.nodes_service = nodes_service
        self.use_rag = use_rag
        self.system_prompt = AIVIS_SYSTEM_PROMPT
    
    def _build_messages(
        self,
        user_message: str,
        session_memory: Optional[List[Dict[str, Any]]] = None,
        context_facts: Optional[List[str]] = None,
        max_history: int = 20,
    ) -> List[Dict[str, str]]:
        """
        Build the messages array for the chat completion.
        
        Parameters
        ----------
        user_message : str
            User's latest message
        session_memory : list, optional
            Recent conversation history
        context_facts : list, optional
            Relevant facts from vector memory
        max_history : int
            Maximum number of history messages to include
            
        Returns
        -------
        list of dict
            Messages in OpenAI format
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add context facts if available
        if context_facts:
            context_text = "\n".join(f"- {fact}" for fact in context_facts[:5])
            context_msg = f"Context about the user:\n{context_text}"
            messages.append({"role": "system", "content": context_msg})
        
        # Add conversation history
        if session_memory:
            for msg in session_memory[-max_history:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if not isinstance(content, str):
                    content = str(content)
                if role in ("user", "assistant", "bot"):
                    messages.append({
                        "role": "assistant" if role == "bot" else role,
                        "content": content
                    })
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def handle_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        session_memory: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle a general chat message.
        
        This is the main entry point for general conversation.
        
        Parameters
        ----------
        user_id : str
            User identifier
        session_id : str
            Session identifier
        user_message : str
            User's message
        session_memory : list, optional
            Recent conversation history (pre-loaded by orchestrator)
        metadata : dict, optional
            Additional metadata (emotion, flags, etc.)
            
        Returns
        -------
        dict
            Response dict with:
            - reply: str - the assistant's response
            - metadata: dict - optional metadata about the response
        """
        try:
            # 1. Retrieve relevant context from memory
            context_facts = self._retrieve_context(user_id, user_message)
            
            # 2. Build messages with system prompt, context, and history
            messages = self._build_messages(
                user_message=user_message,
                session_memory=session_memory,
                context_facts=context_facts,
            )
            
            # 3. Generate response using LLM
            reply = self.llm_service.chat_completion_text(
                messages=messages,
                temperature=0.3,
                max_tokens=768,
            )
            
            # 4. Store conversation in memory (will be done by route handler)
            # The route handler saves to MongoDB; we just return the reply
            
            return {
                "reply": reply,
                "metadata": metadata or {},
            }
            
        except Exception as e:
            print(f"[ERROR] AivisCoreAgent.handle_chat failed: {e}", flush=True)
            return {
                "reply": "I'm having trouble processing your message right now. Please try again.",
                "metadata": {"error": str(e)},
            }
    
    def _retrieve_context(
        self,
        user_id: str,
        query: str,
        max_facts: int = 3,
    ) -> List[str]:
        """
        Retrieve relevant context facts from memory.
        
        Parameters
        ----------
        user_id : str
            User identifier
        query : str
            Query for semantic search
        max_facts : int
            Maximum facts to retrieve
            
        Returns
        -------
        list of str
            Relevant facts
        """
        try:
            # Only retrieve if query is substantial
            if len(query.split()) < 3:
                return []
            
            facts = self.memory_service.search_memory(
                user_id=user_id,
                query=query,
                top_k=max_facts,
            )
            
            if facts:
                print(f"[MEMORY] Retrieved {len(facts)} context facts for user {user_id}")
            
            return facts
        except Exception as e:
            print(f"[ERROR] Failed to retrieve context: {e}", flush=True)
            return []

