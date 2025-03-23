<template>
  <div class="quotation-canvas">
    <div class="quotation-header">
      <h2>Your Quotations</h2>
      <!-- Only show action buttons if there are confirmed quotations -->
      <div v-if="hasConfirmedQuotations" class="quotation-actions">
        <button class="action-button info-button" @click="toggleCustomerForm">
          <span class="button-icon">📋</span>
          {{ showCustomerForm ? "Hide Form" : "Add Customer Info" }}
        </button>
        <button
          class="action-button download-button"
          @click="handleDownloadPDF"
          :disabled="loading"
        >
          <span class="button-icon">📥</span>
          {{ loading ? "Preparing..." : "Download PDF" }}
        </button>
      </div>
    </div>

    <transition name="slide-fade">
      <div v-if="showCustomerForm" class="customer-info-form">
        <div class="form-header">
          <h3>Customer Information</h3>
          <span class="required-note">* Required for PDF download</span>
        </div>
        <div class="form-group">
          <label for="name">Name: <span class="required">*</span></label>
          <input
            type="text"
            id="name"
            v-model="customerInfo.name"
            placeholder="Enter customer name"
            required
            aria-required="true"
          />
        </div>
        <div class="form-group">
          <label for="email">Email: <span class="required">*</span></label>
          <input
            type="email"
            id="email"
            v-model="customerInfo.email"
            placeholder="Enter customer email"
            required
            aria-required="true"
          />
        </div>
        <div class="form-group">
          <label for="phone">Phone:</label>
          <input
            type="tel"
            id="phone"
            v-model="customerInfo.phone"
            placeholder="Enter customer phone"
          />
        </div>
        <div class="form-actions">
          <button
            class="form-button save-button"
            @click="validateAndSaveCustomerInfo"
          >
            Save Information
          </button>
          <button class="form-button cancel-button" @click="toggleCustomerForm">
            Cancel
          </button>
        </div>
      </div>
    </transition>

    <div class="quotations-container">
      <transition name="fade" mode="out-in">
        <div v-if="displayableQuotations.length === 0" class="no-quotations">
          <div class="empty-state-icon">📝</div>
          <p class="empty-state-title">No confirmed quotations yet</p>
          <p class="empty-state-hint">
            Chat with our assistant to get started! Ask about:
          </p>
          <div class="suggestion-chips">
            <button
              v-for="(suggestion, index) in suggestions"
              :key="index"
              class="suggestion-chip"
              @click="sendSuggestion(suggestion)"
            >
              {{ suggestion }}
            </button>
          </div>
        </div>
        <div v-else class="quotations-list">
          <transition-group name="list" tag="div">
            <div
              v-for="(quotation, index) in displayableQuotations"
              :key="quotation.id"
              :class="[
                'quotation-card',
                {
                  confirmed: quotation.confirmed && !quotation.disputed,
                  disputed:
                    quotation.disputed && !isQuotationReplaced(quotation),
                  replaced: isQuotationReplaced(quotation),
                },
              ]"
            >
              <div class="quotation-header-section">
                <div class="quotation-number">Quotation #{{ index + 1 }}</div>
                <div class="quotation-status">
                  <span class="status-indicator"></span>
                  {{ getQuotationStatus(quotation) }}
                </div>
              </div>
              <div class="quotation-content">
                <div
                  v-for="(line, lineIndex) in formatQuotation(
                    quotation.text,
                    quotation.confirmed
                  )"
                  :key="lineIndex"
                  :class="[
                    'quotation-line',
                    {
                      'quotation-title': line.includes('SERVICE QUOTATION'),
                      'quotation-divider': line.includes('------------------'),
                      'quotation-service': line.includes(
                        'Service Description:'
                      ),
                      'quotation-total': line.includes('Total:'),
                    },
                  ]"
                >
                  {{ line }}
                </div>
              </div>
              <!-- Add a dispute button for confirmed quotations that aren't replaced or disputed -->
              <div
                v-if="
                  quotation.confirmed &&
                  !isQuotationReplaced(quotation) &&
                  !quotation.disputed
                "
                class="quotation-actions card-actions"
              >
                <button
                  class="dispute-button"
                  @click="confirmDispute(quotation)"
                >
                  <span class="button-icon">⚠️</span>
                  Dispute This Quotation
                </button>
              </div>
              <!-- Show replacement info if this quotation was replaced -->
              <div
                v-if="isQuotationReplaced(quotation)"
                class="replacement-info"
              >
                <p>This quotation has been replaced with a new version.</p>
              </div>
            </div>
          </transition-group>
        </div>
      </transition>
    </div>

    <!-- Confirmation Dialog -->
    <div v-if="showDisputeDialog" class="dialog-overlay" @click="cancelDispute">
      <div class="dialog-box" @click.stop>
        <h3 class="dialog-title">Confirm Dispute</h3>
        <p class="dialog-message">
          Are you sure you want to dispute this quotation? A replacement will be
          provided.
        </p>
        <div class="dialog-actions">
          <button
            class="dialog-button confirm-button"
            @click="proceedWithDispute"
          >
            Yes, Dispute
          </button>
          <button class="dialog-button cancel-button" @click="cancelDispute">
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
  name: "QuotationCanvas",
  data() {
    return {
      customerInfo: {
        name: "",
        email: "",
        phone: "",
      },
      customerInfoSaved: false,
      showCustomerForm: false,
      replacedDisputedIds: [], // Changed from Set to Array for better reactivity
      showDisputeDialog: false,
      disputeTarget: null,
      suggestions: [
        "Aircon servicing",
        "Aircon installation",
        "Aircon repair",
        "Plumbing services",
      ],
    };
  },
  computed: {
    ...mapState("chat", ["quotations", "loading"]),
    // Add a computed property to check if there are confirmed quotations
    hasConfirmedQuotations() {
      return this.quotations.some((q) => q.confirmed);
    },
    // Add a computed property to filter out pending quotations
    displayableQuotations() {
      // Filter to only show confirmed or disputed quotations
      const filteredQuotations = this.uniqueQuotations.filter(
        (q) => q.confirmed || q.disputed
      );
      return filteredQuotations;
    },
    // Add a computed property to filter out duplicate quotations and handle replacements
    uniqueQuotations() {
      // Create a map to track unique quotation texts
      const uniqueMap = new Map();

      // Process quotations in reverse order (newest first)
      // so that if there are duplicates, we keep the newest one
      [...this.quotations].reverse().forEach((quotation) => {
        // Extract the essential part of the quotation for comparison
        const essentialText = this.getEssentialQuotationText(quotation.text);

        // Only add to map if this essential text isn't already there
        // or if this quotation is confirmed and the existing one isn't
        const existing = uniqueMap.get(essentialText);
        if (!existing || (quotation.confirmed && !existing.confirmed)) {
          uniqueMap.set(essentialText, quotation);
        }
      });

      // Convert map values back to array and reverse to restore original order
      return Array.from(uniqueMap.values()).reverse();
    },
    // Check if customer info is valid for download
    isCustomerInfoValid() {
      return (
        this.customerInfo.name.trim() !== "" &&
        this.customerInfo.email.trim() !== "" &&
        this.validateEmail(this.customerInfo.email)
      );
    },
  },
  watch: {
    quotations: {
      handler(newQuotations, oldQuotations) {
        // If we have more quotations than before, check for replacements
        if (newQuotations.length > oldQuotations.length) {
          this.$nextTick(() => {
            this.checkForReplacements();
          });
        }
      },
      deep: true,
    },
  },
  methods: {
    ...mapActions("chat", ["downloadQuotations", "sendMessage"]),
    ...mapMutations("chat", ["DISPUTE_QUOTATION", "CONFIRM_QUOTATION"]),
    formatQuotation(text, isConfirmed) {
      // If it's a confirmed quotation or contains match score info, clean it up
      if (
        isConfirmed ||
        text.includes("match score") ||
        text.includes("Other similar services")
      ) {
        // Extract only the essential information
        const lines = text.split("\n");
        const essentialLines = [];

        // Keep only the lines we want
        let foundServiceDescription = false;
        let isServiceDescriptionLine = false;

        for (const line of lines) {
          // Always include the header
          if (
            line.includes("SERVICE QUOTATION") ||
            line.includes("------------------")
          ) {
            essentialLines.push(line);
            continue;
          }

          // Include essential information lines
          if (line.includes("Service Description:")) {
            foundServiceDescription = true;
            isServiceDescriptionLine = true;
            essentialLines.push(line);
          } else if (
            isServiceDescriptionLine &&
            !line.includes("Quantity:") &&
            line.trim() &&
            !line.includes("This quotation is") &&
            !line.includes("match score") &&
            !line.includes("Other similar")
          ) {
            // This handles multi-line service descriptions
            essentialLines.push(line);
          } else if (line.includes("Quantity:")) {
            isServiceDescriptionLine = false;
            essentialLines.push(line);
          } else if (
            line.includes("Unit Price (RM):") ||
            line.includes("Subtotal:") ||
            line.includes("Tax (8%):") ||
            line.includes("Total:")
          ) {
            essentialLines.push(line);
          } else if (
            line.includes("This quotation is") ||
            line.includes("match score") ||
            line.includes("Other similar")
          ) {
            // Skip these lines
            continue;
          }
        }

        return essentialLines;
      }

      // If it's not a confirmed quotation, just split by newlines
      return text.split("\n");
    },
    getEssentialQuotationText(text) {
      // Extract just the essential parts of the quotation for comparison
      // This helps identify duplicates even if the surrounding text differs
      let essentialText = "";

      // Extract service description, quantity, price, etc.
      const descMatch = text.match(/Service Description:\s*([^\n]+)/);
      const qtyMatch = text.match(/Quantity:\s*(\d+)/);
      const priceMatch = text.match(/Unit Price \(RM\):\s*([\d\.]+)/);
      const totalMatch = text.match(/Total:\s*([\d\.]+)/);

      if (descMatch) essentialText += descMatch[1];
      if (qtyMatch) essentialText += "|" + qtyMatch[1];
      if (priceMatch) essentialText += "|" + priceMatch[1];
      if (totalMatch) essentialText += "|" + totalMatch[1];

      return essentialText;
    },
    isQuotationReplaced(quotation) {
      // Check if this quotation ID is in the replacedDisputedIds array
      return this.replacedDisputedIds.includes(quotation.id);
    },
    getQuotationStatus(quotation) {
      if (quotation.disputed) {
        if (this.isQuotationReplaced(quotation)) return "Replaced";
        return "Disputed - Awaiting Replacement";
      }
      if (quotation.confirmed) return "Confirmed";
      return "Pending Confirmation";
    },
    toggleCustomerForm() {
      this.showCustomerForm = !this.showCustomerForm;
    },
    validateEmail(email) {
      const re =
        /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
      return re.test(String(email).toLowerCase());
    },
    validateAndSaveCustomerInfo() {
      if (!this.customerInfo.name.trim()) {
        alert("Please enter a customer name");
        return;
      }

      if (!this.customerInfo.email.trim()) {
        alert("Please enter a customer email");
        return;
      }

      if (!this.validateEmail(this.customerInfo.email)) {
        alert("Please enter a valid email address");
        return;
      }

      this.customerInfoSaved = true;

      // Save to localStorage immediately after validation
      try {
        localStorage.setItem("customerInfo", JSON.stringify(this.customerInfo));
      } catch (e) {
        console.error("Could not save customer info to localStorage", e);
      }

      this.showCustomerForm = false;

      // Show success message
      this.$nextTick(() => {
        const toast = document.createElement("div");
        toast.className = "toast-message";
        toast.textContent = "Customer information saved";
        document.body.appendChild(toast);

        setTimeout(() => {
          toast.classList.add("show");
          setTimeout(() => {
            toast.classList.remove("show");
            setTimeout(() => {
              document.body.removeChild(toast);
            }, 300);
          }, 2000);
        }, 100);
      });
    },
    handleDownloadPDF() {
      // Check if customer info is valid
      if (!this.isCustomerInfoValid) {
        this.showCustomerForm = true;
        alert(
          "Please fill in the required customer information before downloading"
        );
        return;
      }

      // Double-check that required fields are filled
      if (
        !this.customerInfo.name.trim() ||
        !this.customerInfo.email.trim() ||
        !this.validateEmail(this.customerInfo.email)
      ) {
        this.showCustomerForm = true;
        alert(
          "Please fill in all required customer information fields with valid data"
        );
        return;
      }
      // Emit an event that ChatInterface will listen for
      emitter.emit("processing-action", "Preparing your document...");

      // This will now pass the customer info to the action
      this.downloadQuotations(this.customerInfo)
        .then(() => {
          // Notify that processing is complete
          emitter.emit("processing-complete");
          this.showToast("Your document has been downloaded successfully.");

          // Save customer info again to ensure it's stored
          this.saveCustomerInfoToStorage();
        })
        .catch((error) => {
          // Notify that processing is complete
          emitter.emit("processing-complete");
          console.error("Error downloading PDF:", error);
          this.showToast(
            "There was an error generating your PDF. Please try again."
          );
        });
    },
    confirmDispute(quotation) {
      this.disputeTarget = quotation;
      this.showDisputeDialog = true;
    },
    cancelDispute() {
      this.showDisputeDialog = false;
      this.disputeTarget = null;
    },
    proceedWithDispute() {
      if (!this.disputeTarget) return;

      const quotation = this.disputeTarget;

      // Mark the quotation as disputed in the store
      this.DISPUTE_QUOTATION(quotation.id);

      // Send a message to the chatbot to inform about the dispute
      this.sendMessage(
        `I'd like to dispute the quotation for "${this.getShortDescription(
          quotation.text
        )}". Please provide a replacement quotation.`
      );

      // Close the dialog
      this.showDisputeDialog = false;
      this.disputeTarget = null;

      // Show a toast notification
      this.showToast(
        "Dispute submitted. A replacement will be provided shortly."
      );
    },
    showToast(message) {
      const toast = document.createElement("div");
      toast.className = "toast-message";
      toast.textContent = message;
      document.body.appendChild(toast);

      setTimeout(() => {
        toast.classList.add("show");
        setTimeout(() => {
          toast.classList.remove("show");
          setTimeout(() => {
            document.body.removeChild(toast);
          }, 300);
        }, 3000);
      }, 100);
    },
    getShortDescription(text) {
      // Extract a short description from the quotation text
      const match = text.match(/Service Description:\s*([^\n]+)/);
      return match ? match[1].substring(0, 30) + "..." : "this service";
    },
    sendSuggestion(suggestion) {
      this.sendMessage(suggestion);
      this.showToast(`Asking about ${suggestion}...`);
    },
    handleConfirmationMessage(message) {
      console.log("Handling confirmation message:", message);
      // Find the most recent unconfirmed quotation
      const unconfirmedQuotation = [...this.quotations]
        .reverse()
        .find((q) => !q.confirmed && !q.disputed);

      if (unconfirmedQuotation) {
        console.log("Confirming quotation:", unconfirmedQuotation.id);
        this.CONFIRM_QUOTATION(unconfirmedQuotation.id);

        // After confirming, check if there are any disputed quotations
        // that should be marked as replaced by this newly confirmed quotation
        const disputedQuotations = this.quotations.filter(
          (q) => q.disputed && !this.isQuotationReplaced(q)
        );

        if (disputedQuotations.length > 0) {
          // Get the most recent disputed quotation
          const mostRecentDisputed = disputedQuotations.sort(
            (a, b) => b.id - a.id
          )[0];

          // Mark it as replaced
          if (!this.replacedDisputedIds.includes(mostRecentDisputed.id)) {
            this.replacedDisputedIds.push(mostRecentDisputed.id);
            console.log(
              `Marked disputed quotation ${mostRecentDisputed.id} as replaced by ${unconfirmedQuotation.id}`
            );

            // Show a toast notification
            this.showToast(
              "A disputed quotation has been replaced with a new version."
            );
          }
        }
      }
    },
    checkForReplacements() {
      // Find all disputed quotations
      const disputedQuotations = this.quotations.filter(
        (q) => q.disputed && !this.isQuotationReplaced(q)
      );

      // If there are no disputed quotations, nothing to do
      if (disputedQuotations.length === 0) return;

      // Find all confirmed quotations (potential replacements)
      const confirmedQuotations = this.quotations.filter(
        (q) => q.confirmed && !q.disputed
      );

      // For each disputed quotation, try to find a replacement
      let replacementsFound = false;

      disputedQuotations.forEach((disputed) => {
        // Find the newest potential replacement that was created after the disputed one
        const replacements = confirmedQuotations.filter(
          (q) => q.id > disputed.id
        );

        if (replacements.length > 0) {
          // Get the newest one
          const replacement = replacements.sort((a, b) => b.id - a.id)[0];

          console.log(
            `Found replacement for disputed quotation ${disputed.id}: ${replacement.id}`
          );

          // Mark the disputed quotation as replaced by adding to the array
          // Only add if not already in the array
          if (!this.replacedDisputedIds.includes(disputed.id)) {
            this.replacedDisputedIds.push(disputed.id);
            replacementsFound = true;
          }
        }
      });

      // If we found replacements, show a notification
      if (replacementsFound) {
        this.showToast(
          "A disputed quotation has been replaced with a new version."
        );
      }
    },
    // Save customer info to localStorage
    saveCustomerInfoToStorage() {
      if (this.customerInfoSaved) {
        try {
          localStorage.setItem(
            "customerInfo",
            JSON.stringify(this.customerInfo)
          );
        } catch (e) {
          console.error("Could not save customer info to localStorage", e);
        }
      }
    },
    // Load customer info from localStorage
    loadCustomerInfoFromStorage() {
      try {
        const savedInfo = localStorage.getItem("customerInfo");
        if (savedInfo) {
          this.customerInfo = JSON.parse(savedInfo);
          this.customerInfoSaved = true;
        }
      } catch (e) {
        console.error("Could not load customer info from localStorage", e);
      }
    },
  },
  mounted() {
    // Listen for confirmation messages - use only one method
    emitter.on("confirmation-message", this.handleConfirmationMessage);

    // Initial check for replacements - only if we have quotations
    if (this.quotations.length > 0) {
      this.checkForReplacements();
    }

    // Load saved customer info if available
    this.loadCustomerInfoFromStorage();

    // Add event listener for beforeunload to save customer info
    window.addEventListener("beforeunload", this.saveCustomerInfoToStorage);
  },
  beforeUnmount() {
    // Clean up event listeners
    emitter.off("confirmation-message", this.handleConfirmationMessage);
    window.removeEventListener("beforeunload", this.saveCustomerInfoToStorage);
  },
};
</script>

<style scoped>
.quotation-canvas {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  position: relative;
}

.quotation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background-color: #f5f5f5;
  border-bottom: 1px solid #ddd;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.quotation-header h2 {
  margin: 0;
  font-size: 20px;
  color: #333;
  font-weight: 600;
}

.quotation-actions {
  display: flex;
  gap: 10px;
}

.action-button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.button-icon {
  font-size: 16px;
}

.info-button {
  background-color: #3498db;
  color: white;
}

.info-button:hover {
  background-color: #2980b9;
}

.download-button {
  background-color: #27ae60;
  color: white;
}

.download-button:hover {
  background-color: #219653;
}

.download-button:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
}

.dispute-button {
  padding: 8px 16px;
  background-color: #e74c3c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  margin: 0 15px 15px 15px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.dispute-button:hover {
  background-color: #c0392b;
  transform: translateY(-1px);
}

.customer-info-form {
  background-color: white;
  border-radius: 8px;
  padding: 20px;
  margin: 15px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.form-header h3 {
  margin: 0;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.required-note {
  font-size: 12px;
  color: #e74c3c;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-size: 14px;
  color: #555;
  font-weight: 500;
}

.required {
  color: #e74c3c;
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.2s ease;
}

.form-group input:focus {
  border-color: #3498db;
  outline: none;
  box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.form-button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.save-button {
  background-color: #3498db;
  color: white;
}

.save-button:hover {
  background-color: #2980b9;
}

.cancel-button {
  background-color: #f1f1f1;
  color: #333;
}

.cancel-button:hover {
  background-color: #e0e0e0;
}

.quotations-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.quotations-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.no-quotations {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #7f8c8d;
  text-align: center;
  padding: 40px 20px;
}

.empty-state-icon {
  font-size: 48px;
  margin-bottom: 15px;
}

.empty-state-title {
  font-size: 18px;
  font-weight: 600;
  color: #34495e;
  margin-bottom: 10px;
}

.empty-state-hint {
  font-size: 14px;
  margin-bottom: 20px;
  color: #7f8c8d;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 10px;
}

.suggestion-chip {
  padding: 8px 16px;
  background-color: #f1f1f1;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s ease;
}

.suggestion-chip:hover {
  background-color: #e0e0e0;
  transform: translateY(-1px);
}

.quotation-card {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  transition: all 0.3s ease;
  position: relative;
}

.quotation-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
}

.quotation-card.confirmed {
  border-left: 4px solid #27ae60;
}

.quotation-card.disputed {
  border-left: 4px solid #e74c3c;
}

.quotation-header-section {
  display: flex;
  flex-direction: column;
}

.quotation-number {
  padding: 12px 15px;
  background-color: #34495e;
  color: white;
  font-weight: 600;
  font-size: 14px;
}

.quotation-status {
  padding: 8px 15px;
  font-size: 12px;
  background-color: #f5f5f5;
  color: #7f8c8d;
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #7f8c8d;
}

.quotation-card.confirmed .quotation-status {
  background-color: #e8f5e9;
  color: #27ae60;
}

.quotation-card.confirmed .status-indicator {
  background-color: #27ae60;
}

.quotation-card.disputed .quotation-status {
  background-color: #fdeaea;
  color: #e74c3c;
}

.quotation-card.disputed .status-indicator {
  background-color: #e74c3c;
}

.quotation-content {
  padding: 15px;
}

.quotation-content {
  padding: 15px;
}

.quotation-line {
  margin-bottom: 5px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.quotation-title {
  font-weight: 600;
  font-size: 16px;
  color: #34495e;
  margin-bottom: 8px;
}

.quotation-divider {
  color: #bdc3c7;
  margin-bottom: 10px;
}

.quotation-service {
  font-weight: 500;
  color: #2c3e50;
}

.quotation-total {
  font-weight: 600;
  color: #2c3e50;
  margin-top: 5px;
}

.quotation-card.disputed.replaced {
  opacity: 0.6;
  border-left: 4px solid #95a5a6;
}

.quotation-card.disputed.replaced .quotation-status {
  background-color: #ecf0f1;
  color: #95a5a6;
}

.quotation-card.disputed.replaced .status-indicator {
  background-color: #95a5a6;
}

.replacement-info {
  padding: 10px 15px;
  background-color: #f8f9fa;
  border-top: 1px solid #ecf0f1;
  font-size: 13px;
  color: #7f8c8d;
  font-style: italic;
}

.card-actions {
  padding: 10px 15px;
  border-top: 1px solid #ecf0f1;
  display: flex;
  justify-content: flex-end;
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
}

.dialog-box {
  background-color: white;
  border-radius: 8px;
  padding: 20px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.dialog-title {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 18px;
  color: #34495e;
}

.dialog-message {
  margin-bottom: 20px;
  line-height: 1.5;
  color: #2c3e50;
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

.confirm-button {
  background-color: #e74c3c;
  color: white;
}

.confirm-button:hover {
  background-color: #c0392b;
}

/* Toast notification */
.toast-message {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  background-color: #333;
  color: white;
  padding: 12px 20px;
  border-radius: 4px;
  font-size: 14px;
  z-index: 1001;
  opacity: 0;
  transition: all 0.3s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.toast-message.show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}

/* Transitions */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.3s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(-20px);
  opacity: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.list-enter-active,
.list-leave-active {
  transition: all 0.5s ease;
}

.list-enter-from {
  opacity: 0;
  transform: translateY(30px);
}

.list-leave-to {
  opacity: 0;
  transform: translateY(-30px);
}

@media (max-width: 768px) {
  .quotation-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 15px;
  }

  .quotation-actions {
    width: 100%;
    justify-content: space-between;
  }

  .action-button {
    padding: 6px 12px;
    font-size: 13px;
  }

  .button-icon {
    font-size: 14px;
  }

  .quotations-container {
    padding: 15px;
  }

  .quotation-card {
    margin-bottom: 15px;
  }

  .suggestion-chips {
    flex-direction: column;
    align-items: center;
  }

  .suggestion-chip {
    width: 100%;
    max-width: 250px;
  }

  .dialog-box {
    width: 95%;
    padding: 15px;
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
  .quotation-canvas {
    color-scheme: dark;
  }

  .quotation-header {
    background-color: #1e1e1e;
    border-bottom-color: #333;
  }

  .quotation-header h2 {
    color: #e0e0e0;
  }

  .customer-info-form {
    background-color: #2d2d2d;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
  }

  .form-header h3 {
    color: #e0e0e0;
  }

  .form-group label {
    color: #ccc;
  }

  .form-group input {
    background-color: #333;
    border-color: #444;
    color: #e0e0e0;
  }

  .form-group input:focus {
    border-color: #3498db;
    box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.3);
  }

  .cancel-button {
    background-color: #333;
    color: #e0e0e0;
  }

  .cancel-button:hover {
    background-color: #444;
  }

  .quotations-container {
    background-color: #1e1e1e;
  }

  .quotation-card {
    background-color: #2d2d2d;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
  }

  .quotation-card:hover {
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
  }

  .quotation-number {
    background-color: #1e1e1e;
  }

  .quotation-status {
    background-color: #333;
    color: #ccc;
  }

  .quotation-card.confirmed .quotation-status {
    background-color: rgba(39, 174, 96, 0.2);
  }

  .quotation-card.disputed .quotation-status {
    background-color: rgba(231, 76, 60, 0.2);
  }

  .quotation-title {
    color: #e0e0e0;
  }

  .quotation-service,
  .quotation-total {
    color: #ccc;
  }

  .replacement-info {
    background-color: #333;
    border-top-color: #444;
  }

  .dialog-box {
    background-color: #2d2d2d;
  }

  .dialog-title {
    color: #e0e0e0;
  }

  .dialog-message {
    color: #ccc;
  }

  .suggestion-chip {
    background-color: #333;
    color: #e0e0e0;
  }

  .suggestion-chip:hover {
    background-color: #444;
  }
}
</style>
