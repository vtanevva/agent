"use client";

import React, { useEffect } from "react";

export default function ConnectGoogleModal({
  isOpen,
  onRequestClose,
  connectUrl,
  onSuccess,
}) {


  if (!isOpen || !connectUrl) return null;

  // Automatically open the popup when the component is shown
  useEffect(() => {
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
  }, [connectUrl, onRequestClose, onSuccess]);

  // Return null since we don't want to show any UI
  return null;
}
