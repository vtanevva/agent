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
    
    // Detect if we're on mobile
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    
    if (isMobile) {
      console.log("Mobile device detected, using direct redirect");
      // On mobile, always use direct redirect as popups are often blocked
      window.location.href = connectUrl;
      return;
    }
    
    // Try popup first for desktop
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
