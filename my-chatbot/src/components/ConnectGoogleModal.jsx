"use client";

import React, { useEffect } from "react";

export default function ConnectGoogleModal({
  isOpen,
  onRequestClose,
  connectUrl,
  onSuccess,
}) {
  if (!isOpen || !connectUrl) return null;

  useEffect(() => {
    console.log("ConnectGoogleModal: Opening OAuth with URL:", connectUrl);
    
    // Try popup first
    const popup = window.open(connectUrl, "GoogleAuth", "width=500,height=600,scrollbars=yes,resizable=yes");
    
    if (!popup) {
      console.log("Popup blocked, using direct redirect");
      // If popup is blocked, use direct redirect
      window.location.href = connectUrl;
      return;
    }

    console.log("Popup opened successfully");
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
