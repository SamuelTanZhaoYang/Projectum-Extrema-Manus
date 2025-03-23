import { chatService } from "@/services/api";
import emitter from "@/eventBus";

const state = {
  messages: [],
  loading: false,
  sessionId: `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  quotation: null,
  quotations: [],
  error: null,
};

const getters = {
  getMessages: (state) => state.messages,
  isLoading: (state) => state.loading,
  getSessionId: (state) => state.sessionId,
  getQuotation: (state) => state.quotation,
  getQuotations: (state) => state.quotations,
  getError: (state) => state.error,
};

const actions = {
  async sendMessage({ commit, state }, message) {
    // Ensure message is a string before checking if it starts with something
    const messageText = String(message || "");

    if (!messageText.trim()) return;

    // Add user message to chat
    commit("ADD_MESSAGE", { text: messageText, sender: "user" });

    // Show loading state
    commit("SET_LOADING", true);
    commit("SET_ERROR", null);

    try {
      const response = await chatService.sendMessage(
        messageText,
        state.sessionId
      );

      // Add bot response to chat
      commit("ADD_MESSAGE", { text: response.data.response, sender: "bot" });

      // Handle quotation if present
      if (response.data.quotation) {
        commit("SET_QUOTATION", response.data.quotation);

        // Check if this quotation already exists
        const existingQuotationIndex = state.quotations.findIndex(
          (q) => q.text === response.data.quotation
        );

        if (existingQuotationIndex === -1) {
          // If quotation doesn't exist, add it
          const newQuotation = {
            id: Date.now(),
            text: response.data.quotation,
            confirmed: false,
            disputed: false,
          };
          commit("ADD_QUOTATION", newQuotation);
        }
      }
    } catch (error) {
      console.error("Error sending message:", error);
      commit("SET_ERROR", "Failed to send message. Please try again.");

      // Add error message to chat
      commit("ADD_MESSAGE", {
        text: "Sorry, there was an error processing your request. Please try again.",
        sender: "bot",
      });
    } finally {
      commit("SET_LOADING", false);
    }
  },

  async resetConversation({ commit, state }) {
    try {
      // Clear messages and quotations first
      commit("RESET_MESSAGES");
      commit("RESET_QUOTATIONS");
      commit("SET_ERROR", null);

      // Add welcome message locally
      commit("ADD_MESSAGE", {
        text: "Hello! I'm your quotation assistant. How can I help you today?",
        sender: "bot",
      });

      // Generate new session ID
      const newSessionId = `session_${Date.now()}_${Math.random()
        .toString(36)
        .substr(2, 9)}`;
      commit("SET_SESSION_ID", newSessionId);

      // Now make the API call to reset the conversation on the server
      await chatService.resetConversation(newSessionId);
    } catch (error) {
      console.error("Error resetting conversation:", error);
      commit("SET_ERROR", "Failed to reset conversation. Please try again.");
    }
  },

  async downloadQuotations({ commit, state }, customerInfo = {}) {
    try {
      commit("SET_LOADING", true);

      // Filter only confirmed and non-disputed quotations
      const confirmedQuotations = state.quotations
        .filter((q) => q.confirmed && !q.disputed)
        .map((q) => q.text);

      // Remove duplicates by converting to a Set and back to an array
      const uniqueQuotations = [...new Set(confirmedQuotations)];

      // Pass the unique confirmed quotations to the API
      await chatService.downloadQuotations(
        state.sessionId,
        customerInfo,
        uniqueQuotations
      );
    } catch (error) {
      console.error("Error downloading quotations:", error);
      commit("SET_ERROR", "Failed to download quotations. Please try again.");
    } finally {
      commit("SET_LOADING", false);
    }
  },
};
const mutations = {
  ADD_MESSAGE(state, message) {
    state.messages.push(message);
  },
  SET_LOADING(state, loading) {
    state.loading = loading;
  },
  SET_SESSION_ID(state, sessionId) {
    state.sessionId = sessionId;
  },
  SET_QUOTATION(state, quotation) {
    state.quotation = quotation;
  },
  ADD_QUOTATION(state, quotation) {
    // Check if this quotation already exists before adding
    const exists = state.quotations.some((q) => q.text === quotation.text);
    if (!exists) {
      state.quotations.push(quotation);
    }
  },
  CONFIRM_QUOTATION(state, payload) {
    if (typeof payload === "string") {
      // If payload is a string (quotation text), find by text
      state.quotations = state.quotations.map((q) =>
        q.text === payload ? { ...q, confirmed: true, disputed: false } : q
      );
    } else if (typeof payload === "number") {
      // If payload is a number (quotation ID), find by ID
      const quotation = state.quotations.find((q) => q.id === payload);
      if (quotation) {
        quotation.confirmed = true;
        quotation.disputed = false; // Clear disputed flag if present
      }
    }
  },
  DISPUTE_QUOTATION(state, quotationId) {
    // Find the quotation by ID and mark it as disputed
    const quotation = state.quotations.find((q) => q.id === quotationId);
    if (quotation) {
      quotation.confirmed = false;
      quotation.disputed = true; // Add a disputed flag for tracking
    }
  },
  SET_ERROR(state, error) {
    state.error = error;
  },
  RESET_MESSAGES(state) {
    state.messages = [];
  },
  RESET_QUOTATIONS(state) {
    state.quotations = [];
    state.quotation = null;
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
