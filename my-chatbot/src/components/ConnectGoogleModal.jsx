"use client";

import React, { useEffect, useState } from "react";

export default function ConnectGoogleModal({
  isOpen,
  onRequestClose,
  connectUrl,
  onSuccess,
}) {
  const [status, setStatus] = useState("idle"); // idle, connecting, popup, redirect, success, error
  const [error, setError] = useState(null);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (!isOpen || !connectUrl) return;

    // Detect mobile device
    const mobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    setIsMobile(mobile);
    setStatus("connecting");

    const handleOAuth = () => {
      try {
    console.log("ConnectGoogleModal: Opening OAuth with URL:", connectUrl);
    
        if (mobile) {
          console.log("Mobile device detected, using system browser");
          setStatus("redirect");
          // Small delay to show the redirect message
          setTimeout(() => {
            // For mobile, we need to open in system browser, not webview
            // Try multiple methods to ensure it opens in system browser
            try {
              // Method 1: Use window.open with _blank
              const newWindow = window.open(connectUrl, '_blank', 'noopener,noreferrer');
              if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
                // Method 2: Create a link and click it
                const link = document.createElement('a');
                link.href = connectUrl;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }
            } catch (e) {
              console.error("Failed to open system browser:", e);
              // Fallback: direct redirect
              window.location.href = connectUrl;
            }
          }, 1000);
          return;
        }
        
        // Try popup first for desktop
        const popup = window.open(
          connectUrl, 
          "GoogleAuth", 
          "width=500,height=600,scrollbars=yes,resizable=yes,top=100,left=100"
        );
        
        if (!popup || popup.closed || typeof popup.closed === 'undefined') {
          console.log("Popup blocked or failed, using direct redirect");
          setStatus("redirect");
          setTimeout(() => {
      window.location.href = connectUrl;
          }, 1000);
      return;
    }

    console.log("Popup opened successfully");
        setStatus("popup");
        
    const timer = setInterval(() => {
          try {
      if (popup.closed) {
        clearInterval(timer);
        console.log("Popup closed, calling success callback");
              setStatus("success");
              setTimeout(() => {
                onRequestClose();
                onSuccess();
              }, 1000);
            }
          } catch (e) {
            // Cross-origin error - popup might be on different domain
            console.log("Cross-origin popup check failed, assuming success");
            clearInterval(timer);
            setStatus("success");
            setTimeout(() => {
        onRequestClose();
        onSuccess();
            }, 1000);
      }
    }, 500);

        // Timeout after 5 minutes
        const timeout = setTimeout(() => {
          clearInterval(timer);
          if (!popup.closed) {
            popup.close();
          }
          setError("Authentication timed out. Please try again.");
          setStatus("error");
        }, 300000); // 5 minutes

        // Cleanup
        return () => {
          clearInterval(timer);
          clearTimeout(timeout);
        };
      } catch (err) {
        console.error("OAuth error:", err);
        setError("Failed to start authentication. Please try again.");
        setStatus("error");
      }
    };

    // Small delay to ensure modal is rendered
    const timer = setTimeout(handleOAuth, 100);
    return () => clearTimeout(timer);
  }, [isOpen, connectUrl, onRequestClose, onSuccess]);

  if (!isOpen || !connectUrl) return null;

  const getStatusMessage = () => {
    switch (status) {
      case "connecting":
        return "Preparing Google authentication...";
      case "popup":
        return "Please complete authentication in the popup window.";
      case "redirect":
        return "Redirecting to Google authentication...";
      case "success":
        return "Authentication successful! Redirecting...";
      case "error":
        return error || "Authentication failed. Please try again.";
      default:
        return "Connecting to Google...";
    }
  };

  const getStatusIcon = () => {
    const iconSize = isMobile ? 'w-12 h-12' : 'w-8 h-8';
    const svgSize = isMobile ? 'w-8 h-8' : 'w-5 h-5';
    
    switch (status) {
      case "connecting":
      case "redirect":
        return (
          <div className={`animate-spin rounded-full border-b-2 border-blue-600 ${iconSize}`}></div>
        );
      case "popup":
        return (
          <div className={`flex items-center justify-center bg-blue-100 rounded-full ${iconSize}`}>
            <svg className={`${svgSize} text-blue-600`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </div>
        );
      case "success":
        return (
          <div className={`flex items-center justify-center bg-green-100 rounded-full ${iconSize}`}>
            <svg className={`${svgSize} text-green-600`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        );
      case "error":
        return (
          <div className={`flex items-center justify-center bg-red-100 rounded-full ${iconSize}`}>
            <svg className={`${svgSize} text-red-600`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        );
      default:
        return (
          <div className={`animate-spin rounded-full border-b-2 border-blue-600 ${iconSize}`}></div>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" />
      
      {/* Modal */}
      <div className={`flex min-h-full items-center justify-center ${
        isMobile ? 'p-0' : 'p-4'
      }`}>
        <div className={`relative bg-white shadow-xl w-full mx-auto transform transition-all ${
          isMobile ? 'h-full max-h-full rounded-none' : 'max-w-md rounded-2xl'
        }`}>
          {/* Header */}
          <div className={`border-b border-gray-200 ${
            isMobile ? 'px-4 py-6' : 'px-6 py-4'
          }`}>
            <div className="flex items-center justify-between">
              <h3 className={`font-semibold text-gray-900 ${
                isMobile ? 'text-xl' : 'text-lg'
              }`}>
                Connect Google Account
              </h3>
              {status !== "connecting" && status !== "redirect" && (
                <button
                  onClick={onRequestClose}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                  disabled={status === "popup"}
                >
                  <svg className={`${isMobile ? 'w-8 h-8' : 'w-6 h-6'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Content */}
          <div className={`${
            isMobile ? 'px-4 py-8 flex-1 flex flex-col justify-center' : 'px-6 py-8'
          }`}>
            <div className="text-center">
              {/* Status Icon */}
              <div className={`flex justify-center ${
                isMobile ? 'mb-6' : 'mb-4'
              }`}>
                {getStatusIcon()}
              </div>

              {/* Status Message */}
              <p className={`text-gray-700 ${
                isMobile ? 'text-lg mb-8' : 'mb-6'
              }`}>
                {getStatusMessage()}
              </p>

              {/* Additional Info */}
              {status === "popup" && (
                <div className={`bg-blue-50 border border-blue-200 rounded-lg mb-4 ${
                  isMobile ? 'p-6' : 'p-4'
                }`}>
                  <p className={`text-blue-800 ${
                    isMobile ? 'text-base' : 'text-sm'
                  }`}>
                    <strong>Tip:</strong> If the popup doesn't appear, check if your browser is blocking popups for this site.
                  </p>
                </div>
              )}

              {status === "redirect" && (
                <div className={`bg-yellow-50 border border-yellow-200 rounded-lg mb-4 ${
                  isMobile ? 'p-6' : 'p-4'
                }`}>
                  <p className={`text-yellow-800 ${
                    isMobile ? 'text-base' : 'text-sm'
                  }`}>
                    <strong>Mobile:</strong> Opening Google authentication in your system browser. Complete the authentication and return to this app.
                  </p>
                </div>
              )}

              {status === "error" && (
                <div className="space-y-4">
                  <div className={`bg-red-50 border border-red-200 rounded-lg ${
                    isMobile ? 'p-6' : 'p-4'
                  }`}>
                    <p className={`text-red-800 ${
                      isMobile ? 'text-base' : 'text-sm'
                    }`}>
                      {error}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setStatus("idle");
                      setError(null);
                      // Retry the OAuth flow
                      setTimeout(() => {
                        setStatus("connecting");
                        window.location.href = connectUrl;
                      }, 100);
                    }}
                    className={`w-full bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors ${
                      isMobile ? 'py-4 px-6 text-lg' : 'py-2 px-4'
                    }`}
                  >
                    Try Again
                  </button>
                </div>
              )}

              {/* Cancel Button */}
              {status !== "success" && status !== "redirect" && (
                <button
                  onClick={onRequestClose}
                  className={`text-gray-500 hover:text-gray-700 transition-colors ${
                    isMobile ? 'text-base mt-4' : 'text-sm'
                  }`}
                  disabled={status === "popup"}
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
