"use client";

import React, { useEffect } from "react";

export default function ConnectGoogleModal({
  isOpen,
  onRequestClose,
  connectUrl,
  onSuccess,
}) {
  if (!isOpen || !connectUrl) return null;

  // Always use popup for now (we'll handle mobile differently)
  useEffect(() => {
    console.log("Opening Google OAuth popup:", connectUrl);
    const popup = window.open(connectUrl, "GoogleAuth", "width=500,height=600,scrollbars=yes,resizable=yes");
    
    if (!popup) {
      console.error("Popup blocked! Trying direct redirect...");
      // If popup is blocked, try direct redirect
      window.location.href = connectUrl;
      return;
    }

    const timer = setInterval(() => {
      if (popup.closed) {
        clearInterval(timer);
        console.log("Popup closed, calling success callback");
        onRequestClose();
        onSuccess();
      }
    }, 500);

    // Cleanup timer if component unmounts
    return () => clearInterval(timer);
  }, [connectUrl, onRequestClose, onSuccess]);

  // Return null since we don't want to show any UI
  return null;
}
