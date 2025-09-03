import { useState, useRef, useEffect } from "react";

export default function Dropdown({
  sessions = [],               // Array of { session_id, name }
  selectedSession,
  onSelect,                    // Will be passed session_id
}) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={dropdownRef} className="relative mb-3">
      {/* Trigger Button */}
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 bg-white/10 border border-white/30 text-white rounded-lg flex items-center justify-center focus:outline-none"
      >
        <svg
          className={`w-3 h-3 transform transition-transform ${
            open ? "rotate-180" : "rotate-90"
          }`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      {/* Dropdown List */}
      {open && (
        <ul className="absolute left-0 mt-2 w-44 max-h-40 overflow-y-auto bg-gradient-to-br from-purple-800 via-indigo-900 to-pink-900 text-white text-sm rounded-lg shadow-lg z-50">
          {sessions.map((s) => (
            <li
              key={s.session_id}
              onClick={() => {
                onSelect(s.session_id);
                setOpen(false);
              }}
              className={`px-3 py-2 hover:bg-white/20 cursor-pointer ${
                selectedSession === s.session_id ? "bg-white/30 text-white font-medium" : ""
              }`}
            >
              {s.name || s.session_id.slice(-8)} {/* fallback if no name */}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
