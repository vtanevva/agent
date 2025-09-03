import { useState, useRef, useEffect } from "react";

export default function Dropdown({
  sessions = [],
  selectedSession,
  onSelect,
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
<ul className="custom-scrollbar absolute left-0 mt-2 w-40 max-h-28 overflow-y-auto bg-white/10 backdrop-blur-md text-gray-200 text-sm rounded-xl shadow-lg z-50 border border-white/20">
          {sessions.map((s) => (
            <li
              key={s}
              onClick={() => {
                onSelect(s);
                setOpen(false);
              }}
              className={`px-3 py-2 hover:bg-white/20 cursor-pointer ${
                selectedSession === s ? "bg-white/30 text-white font-medium" : ""
              }`}
            >
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
