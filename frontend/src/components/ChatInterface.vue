<template>
  <div class="chat-interface">
    <div v-if="error" class="error-message">
      <span class="error-icon">⚠️</span>
      <span>{{ error }}</span>
      <button class="dismiss-error" @click="dismissError">×</button>
    </div>
    <div class="chat-messages" ref="messagesContainer">
      <transition-group name="message-fade">
        <div
          v-for="(message, index) in messages"
          :key="'msg-' + index"
          :class="[
            'message',
            message.sender,
            { 'with-actions': message.actions },
          ]"
        >
          <div
            class="message-content"
            v-html="formatMessage(message.text)"
          ></div>

          <div v-if="message.actions" class="message-actions">
            <button
              v-for="(action, actionIndex) in message.actions"
              :key="'action-' + actionIndex"
              @click="handleActionClick(action)"
              class="message-action-button"
            >
              {{ action.label }}
            </button>
          </div>
        </div>
        <div v-if="loading" key="loading-indicator" class="message bot loading">
          <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </transition-group>
      <div ref="messagesEnd"></div>
    </div>

    <div v-if="processingAction" class="processing-overlay">
      <div class="processing-content">
        <div class="processing-spinner"></div>
        <p>{{ processingMessage }}</p>
      </div>
    </div>

    <div v-if="showQuickReplies && !recentlyConfirmed" class="quick-replies">
      <template v-if="lastMessage && lastMessage.text.includes('confirm')">
        <button @click="handleQuickReply('Confirm')" class="confirm-button">
          <span class="button-icon">✓</span> Confirm
        </button>
        <button
          @click="handleQuickReply('No, I need changes')"
          class="change-button"
        >
          <span class="button-icon">✎</span> Need Changes
        </button>
      </template>
      <template
        v-else-if="
          lastMessage &&
          lastMessage.text.includes(
            'Would you like to get a quotation for any other service?'
          )
        "
      >
        <button @click="handleQuickReply('Yes')" class="yes-button">
          <span class="button-icon">✓</span> Yes
        </button>
        <button @click="handleQuickReply('No')" class="no-button">
          <span class="button-icon">✗</span> No
        </button>
      </template>
      <template v-else-if="suggestedReplies.length > 0">
        <button
          v-for="(reply, index) in suggestedReplies"
          :key="index"
          @click="handleQuickReply(reply)"
          class="suggestion-button"
        >
          {{ reply }}
        </button>
      </template>
    </div>

    <div class="chat-input">
      <div class="input-wrapper">
        <input
          type="text"
          v-model="inputMessage"
          @keypress.enter="handleSendMessage"
          placeholder="Type your message..."
          :disabled="loading || processingAction"
          ref="messageInput"
        />
        <button
          v-if="inputMessage.trim()"
          @click="clearInput"
          class="clear-input"
          :disabled="loading || processingAction"
        >
          ×
        </button>
      </div>
      <button
        @click="handleSendMessage"
        :disabled="loading || processingAction || !inputMessage.trim()"
        class="send-button"
        aria-label="Send message"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </button>
      <button
        @click="showResetConfirmation = true"
        class="reset-button"
        :disabled="loading || processingAction"
        aria-label="New chat"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M21 12a9 9 0 0 1-9 9"></path>
          <path d="M3 12a9 9 0 0 1 9-9"></path>
          <path d="M21 12H3"></path>
          <path d="M12 3v9"></path>
        </svg>
      </button>
    </div>

    <!-- Reset Confirmation Dialog -->
    <div
      v-if="showResetConfirmation"
      class="dialog-overlay"
      @click="showResetConfirmation = false"
    >
      <div class="dialog-box" @click.stop>
        <h3 class="dialog-title">Start New Chat?</h3>
        <p class="dialog-message">
          This will clear your current conversation. Are you sure you want to
          start a new chat?
        </p>
        <div class="dialog-actions">
          <button class="dialog-button confirm-button" @click="confirmReset">
            Yes, Start New Chat
          </button>
          <button
            class="dialog-button cancel-button"
            @click="showResetConfirmation = false"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { mapState, mapActions, mapMutations } from "vuex";
import emitter from "@/eventBus";

export default {
  name: "ChatInterface",
  data() {
    return {
      inputMessage: "",
      recentlyConfirmed: false, // Track if user recently confirmed
      confirmationTimeout: null, // For clearing the timeout
      showResetConfirmation: false, // For reset confirmation dialog
      processingAction: false, // For showing processing state
      processingMessage: "Processing your request...", // Default processing message
      suggestedReplies: [], // Dynamic suggested replies
    };
  },
  computed: {
    ...mapState("chat", ["messages", "loading", "error"]),
    lastMessage() {
      return this.messages.length > 0
        ? this.messages[this.messages.length - 1]
        : null;
    },
    showQuickReplies() {
      return (
        this.lastMessage &&
        this.lastMessage.sender === "bot" &&
        (this.lastMessage.text.includes("confirm") ||
          this.lastMessage.text.includes("Would you like to get a quotation") ||
          this.suggestedReplies.length > 0)
      );
    },
  },
  methods: {
    ...mapActions("chat", [
      "sendMessage",
      "resetConversation",
      "downloadQuotations",
    ]),
    ...mapMutations("chat", ["CLEAR_ERROR"]),

    // Scroll to bottom of messages
    scrollToBottom() {
      this.$nextTick(() => {
        if (this.$refs.messagesEnd) {
          this.$refs.messagesEnd.scrollIntoView({ behavior: "smooth" });
        }
      });
    },

    handleSendMessage() {
      if (this.inputMessage.trim()) {
        const message = this.inputMessage.trim();

        // Check if this is a confirmation message
        const isConfirmation =
          message.toLowerCase() === "confirm" ||
          message.toLowerCase() === "yes" ||
          message.toLowerCase().includes("confirm");

        // If it's a confirmation, hide the quick reply buttons
        if (isConfirmation) {
          this.hideConfirmationButtons();

          // Emit the confirmation event
          emitter.emit("confirmation-message", message);
        }

        // Clear the input field first
        const messageToSend = this.inputMessage;
        this.inputMessage = "";

        // Send the message to the backend
        this.sendMessage(messageToSend);

        // Clear suggested replies
        this.suggestedReplies = [];
      }
    },

    handleQuickReply(reply) {
      // If this is a confirmation, hide the quick reply buttons
      if (reply.toLowerCase() === "confirm" || reply.toLowerCase() === "yes") {
        this.hideConfirmationButtons();

        // Emit the confirmation event
        emitter.emit("confirmation-message", reply);
      }

      // Send the reply to the backend
      this.sendMessage(reply);

      // Clear suggested replies
      this.suggestedReplies = [];
    },

    hideConfirmationButtons() {
      // Set the flag to hide confirmation buttons
      this.recentlyConfirmed = true;

      // Clear any existing timeout
      if (this.confirmationTimeout) {
        clearTimeout(this.confirmationTimeout);
      }

      // Reset the flag after a delay (in case user wants to confirm another quotation later)
      this.confirmationTimeout = setTimeout(() => {
        this.recentlyConfirmed = false;
      }, 10000); // 10 seconds
    },

    formatMessage(text) {
      // Convert URLs to clickable links
      const urlRegex = /(https?:\/\/[^\s]+)/g;
      let formattedText = text.replace(
        urlRegex,
        (url) =>
          `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
      );

      // Convert line breaks to <br>
      formattedText = formattedText.replace(/\n/g, "<br>");

      // Highlight important information
      formattedText = formattedText.replace(
        /(Total:.*)/g,
        '<strong class="highlight-total">$1</strong>'
      );

      return formattedText;
    },

    dismissError() {
      this.CLEAR_ERROR();
    },

    clearInput() {
      this.inputMessage = "";
      this.$refs.messageInput.focus();
    },

    confirmReset() {
      this.showResetConfirmation = false;
      this.resetConversation();
      this.suggestedReplies = [];
    },

    handleActionClick(action) {
      if (action.type === "download") {
        // Check if customer info is available in localStorage
        let customerInfo = { name: "", email: "", phone: "" };
        let isValid = false;

        try {
          const savedInfo = localStorage.getItem("customerInfo");
          if (savedInfo) {
            customerInfo = JSON.parse(savedInfo);
            isValid =
              customerInfo.name &&
              customerInfo.email &&
              this.validateEmail(customerInfo.email);
          }
        } catch (e) {
          console.error("Could not load customer info from localStorage", e);
        }

        if (!isValid) {
          // Show message about needing customer info
          this.sendMessage(
            "Please add customer information before downloading. Click 'Add Customer Info' in the quotations panel."
          );
          return;
        }

        this.showProcessingOverlay("Preparing your document...");

        // Download the quotations
        this.downloadQuotations(customerInfo)
          .then(() => {
            this.hideProcessingOverlay();
            this.sendMessage("Thank you for downloading the quotation.");
          })
          .catch((error) => {
            this.hideProcessingOverlay();
            this.sendMessage(
              "There was an error generating your PDF. Please try again or add customer information first."
            );
          });
      } else if (action.type === "suggest") {
        // Set suggested replies
        this.suggestedReplies = action.suggestions || [];
      } else if (action.type === "dispute") {
        this.showProcessingOverlay("Processing your dispute...");

        setTimeout(() => {
          this.hideProcessingOverlay();
          this.sendMessage(
            `I'd like to dispute the quotation for "${action.service}". Please provide a replacement quotation.`
          );
        }, 1000);
      }
    },

    // Add this helper method
    validateEmail(email) {
      const re =
        /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
      return re.test(String(email).toLowerCase());
    },

    showProcessingOverlay(message) {
      this.processingMessage = message || "Processing your request...";
      this.processingAction = true;
    },

    hideProcessingOverlay() {
      this.processingAction = false;
    },

    analyzeBotMessage(message) {
      // Check for potential suggested replies
      if (message.includes("Would you like to know more about")) {
        this.suggestedReplies = ["Yes, tell me more", "No, thank you"];
      } else if (message.includes("Do you need any other services")) {
        this.suggestedReplies = ["Yes, I need more services", "No, that's all"];
      } else if (message.includes("aircon") && message.includes("services")) {
        this.suggestedReplies = [
          "Aircon servicing",
          "Aircon repair",
          "Aircon installation",
        ];
      } else {
        // Clear suggested replies if no match
        this.suggestedReplies = [];
      }

      // Add message actions if appropriate
      const messageIndex = this.messages.length - 1;
      if (messageIndex >= 0) {
        // Check if this message contains a quotation
        if (
          message.includes("SERVICE QUOTATION") &&
          message.includes("Total:")
        ) {
          // Add actions to the message
          this.$set(this.messages[messageIndex], "actions", [
            { type: "download", label: "Download PDF" },
            {
              type: "dispute",
              label: "Dispute Quotation",
              service: this.extractServiceName(message),
            },
          ]);
        }

        // Check if this is a service suggestion message
        if (
          message.includes("We offer various services") ||
          message.includes("Here are some services")
        ) {
          this.$set(this.messages[messageIndex], "actions", [
            {
              type: "suggest",
              label: "Show Options",
              suggestions: [
                "Aircon servicing",
                "Aircon repair",
                "Aircon installation",
                "Plumbing services",
              ],
            },
          ]);
        }
      }
    },

    extractServiceName(message) {
      const match = message.match(/Service Description:\s*([^\n]+)/);
      return match ? match[1].substring(0, 30) + "..." : "this service";
    },

    // Keyboard shortcuts handler
    handleKeyboardShortcuts(event) {
      // Ctrl/Cmd + Enter to send message
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        this.handleSendMessage();
      }

      // Escape to clear input
      if (event.key === "Escape") {
        if (this.showResetConfirmation) {
          this.showResetConfirmation = false;
        } else if (this.processingAction) {
          // Do nothing when processing
        } else if (this.inputMessage) {
          this.clearInput();
        }
      }
    },
  },
  watch: {
    messages: {
      handler(newMessages, oldMessages) {
        this.scrollToBottom();

        // If we have a new message from the bot
        if (newMessages.length > oldMessages.length) {
          const latestMessage = newMessages[newMessages.length - 1];

          if (latestMessage && latestMessage.sender === "bot") {
            // Analyze the message for potential actions or suggestions
            this.analyzeBotMessage(latestMessage.text);

            // If the bot is asking for confirmation of a new quotation, reset the recentlyConfirmed flag
            if (
              latestMessage.text.includes("confirm") &&
              latestMessage.text.includes("quotation") &&
              !latestMessage.text.includes("Thank you for confirming")
            ) {
              this.recentlyConfirmed = false;
            }
          }
        }
      },
      deep: true,
    },
    loading(newValue) {
      // When loading changes to false, focus the input field
      if (!newValue) {
        this.$nextTick(() => {
          if (this.$refs.messageInput) {
            this.$refs.messageInput.focus();
          }
        });
      }
    },
  },
  mounted() {
    // Add welcome message if no messages exist
    if (this.messages.length === 0) {
      this.resetConversation();
    }

    // Scroll to bottom of messages
    this.scrollToBottom();

    // Focus the input field
    this.$nextTick(() => {
      if (this.$refs.messageInput) {
        this.$refs.messageInput.focus();
      }
    });

    // Listen for keyboard shortcuts
    window.addEventListener("keydown", this.handleKeyboardShortcuts);

    // Listen for processing events from QuotationCanvas
    emitter.on("processing-action", this.showProcessingOverlay);
    emitter.on("processing-complete", this.hideProcessingOverlay);
  },
  beforeUnmount() {
    // Clear any pending timeout
    if (this.confirmationTimeout) {
      clearTimeout(this.confirmationTimeout);
    }

    // Remove event listeners
    window.removeEventListener("keydown", this.handleKeyboardShortcuts);

    // Remove emitter listeners
    emitter.off("processing-action", this.showProcessingOverlay);
    emitter.off("processing-complete", this.hideProcessingOverlay);
  },
};
</script>

<style scoped>
.chat-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  position: relative;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
    Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
}

.error-message {
  background-color: #ffebee;
  color: #c62828;
  padding: 12px 15px;
  margin: 10px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  animation: slideDown 0.3s ease-out;
}

.error-icon {
  margin-right: 8px;
  font-size: 16px;
}

.dismiss-error {
  margin-left: auto;
  background: none;
  border: none;
  color: #c62828;
  font-size: 18px;
  cursor: pointer;
  padding: 0 5px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-behavior: smooth;
  background-color: #f9f9f9;
  background-image: linear-gradient(
      rgba(255, 255, 255, 0.7) 1px,
      transparent 1px
    ),
    linear-gradient(90deg, rgba(255, 255, 255, 0.7) 1px, transparent 1px);
  background-size: 20px 20px;
}

.message {
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 18px;
  margin-bottom: 2px;
  word-wrap: break-word;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
  position: relative;
}

.message.with-actions {
  padding-bottom: 8px;
}

.message-content {
  line-height: 1.5;
}

.message-content a {
  color: #0366d6;
  text-decoration: none;
}

.message-content a:hover {
  text-decoration: underline;
}

.message-content .highlight-total {
  color: #e91e63;
  font-weight: 600;
}

.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.message-action-button {
  padding: 6px 12px;
  background-color: #f1f1f1;
  border: none;
  border-radius: 16px;
  font-size: 12px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s ease;
}

.message-action-button:hover {
  background-color: #e0e0e0;
}

.message.user {
  align-self: flex-end;
  background-color: #0084ff;
  color: white;
  border-bottom-right-radius: 4px;
}

.message.bot {
  align-self: flex-start;
  background-color: white;
  color: #333;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px;
}

.typing-indicator span {
  display: inline-block;
  width: 8px;
  height: 8px;
  background-color: #888;
  border-radius: 50%;
  animation: typing 1s infinite ease-in-out;
}

.message.loading {
  min-width: 60px;
  padding: 8px 12px;
  animation: pulse 1.5s infinite;
  background-color: white;
  align-self: flex-start;
  border-bottom-left-radius: 4px;
}

.typing-indicator span:nth-child(1) {
  animation-delay: 0s;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-5px);
  }
}

.quick-replies {
  display: flex;
  gap: 10px;
  padding: 12px 15px;
  justify-content: center;
  background-color: #f9f9f9;
  border-top: 1px solid #eee;
  flex-wrap: wrap;
  animation: fadeIn 0.3s ease-out;
}

.quick-replies button {
  padding: 8px 16px;
  background-color: white;
  border: 1px solid #0084ff;
  color: #0084ff;
  border-radius: 18px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.quick-replies button:hover {
  background-color: #0084ff;
  color: white;
  transform: translateY(-1px);
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.15);
}

.button-icon {
  font-size: 14px;
}

.confirm-button {
  background-color: #e8f5e9 !important;
  border-color: #4caf50 !important;
  color: #4caf50 !important;
}

.confirm-button:hover {
  background-color: #4caf50 !important;
  color: white !important;
}

.change-button {
  background-color: #fff8e1 !important;
  border-color: #ffc107 !important;
  color: #ffa000 !important;
}

.change-button:hover {
  background-color: #ffc107 !important;
  color: white !important;
}

.yes-button {
  background-color: #e8f5e9 !important;
  border-color: #4caf50 !important;
  color: #4caf50 !important;
}

.yes-button:hover {
  background-color: #4caf50 !important;
  color: white !important;
}

.no-button {
  background-color: #ffebee !important;
  border-color: #f44336 !important;
  color: #f44336 !important;
}

.no-button:hover {
  background-color: #f44336 !important;
  color: white !important;
}

.suggestion-button {
  background-color: #e3f2fd !important;
  border-color: #2196f3 !important;
  color: #2196f3 !important;
}

.suggestion-button:hover {
  background-color: #2196f3 !important;
  color: white !important;
}

.chat-input {
  display: flex;
  padding: 15px;
  border-top: 1px solid #ddd;
  background-color: white;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
  gap: 10px;
}

.input-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}

.chat-input input {
  flex: 1;
  padding: 12px 40px 12px 15px;
  border: 1px solid #ddd;
  border-radius: 24px;
  outline: none;
  font-size: 16px;
  background-color: #f5f5f5;
  transition: all 0.2s ease;
  width: 100%;
}

.chat-input input:focus {
  border-color: #0084ff;
  background-color: white;
  box-shadow: 0 0 0 2px rgba(0, 132, 255, 0.2);
}

.clear-input {
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  color: #999;
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.clear-input:hover {
  background-color: #eee;
  color: #666;
}

.chat-input button {
  padding: 0;
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chat-input .send-button {
  background-color: #0084ff;
  color: white;
}

.chat-input .send-button:hover {
  background-color: #0077e6;
  transform: translateY(-1px);
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
}

.chat-input .reset-button {
  background-color: #f5f5f5;
  color: #666;
}

.chat-input .reset-button:hover {
  background-color: #e0e0e0;
  transform: translateY(-1px);
}

.chat-input button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
  opacity: 0.7;
  transform: none !important;
  box-shadow: none !important;
}

/* Processing overlay */
.processing-overlay {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background-color: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 12px 20px;
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  animation: fadeIn 0.3s ease-out;
}

.processing-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.processing-spinner {
  width: 20px;
  height: 20px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top: 3px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Dialog styles */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
}

.dialog-box {
  background-color: white;
  border-radius: 12px;
  padding: 20px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  animation: scaleIn 0.2s ease-out;
}

.dialog-title {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 18px;
  color: #333;
}

.dialog-message {
  margin-bottom: 20px;
  line-height: 1.5;
  color: #555;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.dialog-button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.dialog-button.confirm-button {
  background-color: #0084ff;
  color: white;
}

.dialog-button.confirm-button:hover {
  background-color: #0077e6;
}

.dialog-button.cancel-button {
  background-color: #f1f1f1;
  color: #333;
}

.dialog-button.cancel-button:hover {
  background-color: #e0e0e0;
}

/* Animations */
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes scaleIn {
  from {
    transform: scale(0.9);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes slideDown {
  from {
    transform: translateY(-20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes pulse {
  0% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.6;
  }
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.message-fade-enter-active,
.message-fade-leave-active {
  transition: all 0.3s;
}

.message-fade-enter-from,
.message-fade-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

/* Loading animation */
.message.loading {
  animation: pulse 1.5s infinite;
}
/* Mobile responsiveness */
@media (max-width: 768px) {
  .message {
    max-width: 90%;
  }

  .chat-input {
    padding: 10px;
  }

  .chat-input input {
    padding: 10px 35px 10px 12px;
    font-size: 14px;
  }

  .chat-input button {
    width: 40px;
    height: 40px;
  }

  .quick-replies {
    padding: 10px;
    overflow-x: auto;
    justify-content: flex-start;
  }

  .quick-replies button {
    padding: 6px 12px;
    font-size: 13px;
    white-space: nowrap;
  }

  .dialog-box {
    width: 95%;
    padding: 15px;
  }

  .message-actions {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .message-action-button {
    width: 100%;
  }
}

/* Accessibility improvements */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .chat-interface {
    color-scheme: dark;
  }

  .chat-messages {
    background-color: #1e1e1e;
    background-image: linear-gradient(
        rgba(255, 255, 255, 0.05) 1px,
        transparent 1px
      ),
      linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  }

  .message.bot {
    background-color: #2d2d2d;
    color: #e0e0e0;
  }

  .message.user {
    background-color: #0084ff;
    color: white;
  }

  .chat-input {
    background-color: #1e1e1e;
    border-top-color: #333;
  }

  .chat-input input {
    background-color: #2d2d2d;
    border-color: #444;
    color: #e0e0e0;
  }

  .chat-input input:focus {
    border-color: #0084ff;
    background-color: #333;
  }

  .chat-input .reset-button {
    background-color: #333;
    color: #ccc;
  }

  .chat-input .reset-button:hover {
    background-color: #444;
  }

  .quick-replies {
    background-color: #1e1e1e;
    border-top-color: #333;
  }

  .quick-replies button {
    background-color: #2d2d2d;
    border-color: #0084ff;
    color: #0084ff;
  }

  .dialog-box {
    background-color: #2d2d2d;
    color: #e0e0e0;
  }

  .dialog-title {
    color: #e0e0e0;
  }

  .dialog-message {
    color: #ccc;
  }

  .dialog-button.cancel-button {
    background-color: #333;
    color: #e0e0e0;
  }

  .dialog-button.cancel-button:hover {
    background-color: #444;
  }

  .message-action-button {
    background-color: #333;
    color: #e0e0e0;
  }

  .message-action-button:hover {
    background-color: #444;
  }

  .message-content .highlight-total {
    color: #ff80ab;
  }
}
</style>
