"use client";

import React, { useEffect, useState } from "react";

export default function ConnectGoogleModal({
  isOpen,
  onRequestClose,
  connectUrl,
  onSuccess,
}) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    // Detect if user is on mobile
    const checkMobile = () => {
      return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    };
    setIsMobile(checkMobile());
  }, []);

  if (!isOpen || !connectUrl) return null;

  // Handle OAuth flow based on device type
  useEffect(() => {
    if (isMobile) {
      // On mobile, redirect directly (no popup)
      window.location.href = connectUrl;
    } else {
      // On desktop, use popup
      const popup = window.open(connectUrl, "GoogleAuth", "width=500,height=600");
      if (popup) {
        const timer = setInterval(() => {
          if (popup.closed) {
            clearInterval(timer);
            onRequestClose();
            onSuccess();
          }
        }, 500);
      }
    }
  }, [connectUrl, onRequestClose, onSuccess, isMobile]);

  // Show loading message on mobile
  if (isMobile) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-sm mx-4">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Connecting to Google
            </h3>
            <p className="text-gray-600 text-sm">
              Redirecting to Google for authentication...
            </p>
            <button
              onClick={onRequestClose}
              className="mt-4 px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Return null for desktop (popup handles everything)
  return null;
}
