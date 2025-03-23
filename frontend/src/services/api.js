import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  timeout: 30000, // 30 seconds timeout for LLM processing
  headers: {
    "Content-Type": "application/json",
  },
});

// Add request interceptor for handling loading states globally
api.interceptors.request.use(
  (config) => {
    // You could dispatch a loading action here
    console.log("API Request:", config.method, config.url, config.data);
    return config;
  },
  (error) => {
    console.error("Request error:", error);
    return Promise.reject(error);
  }
);

// Add response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    console.log("API Response:", response.status, response.data);
    return response;
  },
  (error) => {
    // Handle specific error cases
    if (error.response) {
      // Server responded with error status
      console.error(
        "Server error:",
        error.response.status,
        error.response.data
      );
    } else if (error.request) {
      // Request made but no response received
      console.error("Network error - no response received");
    } else {
      // Error in setting up the request
      console.error("Request error:", error.message);
    }
    return Promise.reject(error);
  }
);

// Chat functions
export const chatService = {
  sendMessage: (message, sessionId) => {
    // Ensure parameters are strings and log the original types
    console.log("Original message type:", typeof message, message);

    // Handle event objects
    if (
      message &&
      typeof message === "object" &&
      message.toString().includes("[object ")
    ) {
      console.error("Received object instead of string message");
      message = "";
    }

    const messageText = String(message || "");
    const sessionIdText = String(sessionId || "default");

    console.log("Sending message to API:", {
      message: messageText,
      session_id: sessionIdText,
    });

    return api.post("/chat", {
      message: messageText,
      session_id: sessionIdText,
    });
  },

  resetConversation: (sessionId) => {
    const sessionIdText = String(sessionId || "default");
    return api.post("/chat/reset", { session_id: sessionIdText });
  },

  downloadQuotations(sessionId, customerInfo, quotations = []) {
    const params = new URLSearchParams();
    params.append("session_id", sessionId);
    params.append("format", "pdf");

    if (customerInfo.name) params.append("customer_name", customerInfo.name);
    if (customerInfo.email) params.append("customer_email", customerInfo.email);
    if (customerInfo.phone) params.append("customer_phone", customerInfo.phone);

    // Add quotations as a JSON string
    if (quotations && quotations.length > 0) {
      params.append("quotations", JSON.stringify(quotations));
    }

    // Create a URL with the parameters - use the same baseURL from axios
    const baseURL = import.meta.env.VITE_API_URL || "/api";
    const url = `${baseURL}/quotations/download?${params.toString()}`;

    // Open the URL in a new window or trigger download
    window.open(url, "_blank");

    return Promise.resolve();
  },
};

export default api;
