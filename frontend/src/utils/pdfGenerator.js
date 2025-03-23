import { jsPDF } from "jspdf";
import "jspdf-autotable"; // Import this way for auto-registration
import store from "@/store"; // Import your Vuex store
import { chatService } from "@/services/api"; // Make sure this is imported

export const generateQuotationPDF = (quotations, customerInfo = {}) => {
  try {
    // Create a new PDF document
    const doc = new jsPDF();

    // Check if autoTable is available
    if (typeof doc.autoTable !== "function") {
      console.error("autoTable is not a function on the jsPDF instance");
      throw new Error("jspdf-autotable is not properly loaded");
    }

    // Add company header
    doc.setFontSize(20);
    doc.setTextColor(0, 0, 128);
    doc.text("Service Quotation System", 105, 20, { align: "center" });

    // Add company details
    doc.setFontSize(10);
    doc.setTextColor(100, 100, 100);
    doc.text("123 Service Road, Business District", 105, 30, {
      align: "center",
    });
    doc.text(
      "Phone: +123-456-7890 | Email: info@servicequotation.com",
      105,
      35,
      {
        align: "center",
      }
    );

    // Add customer information if available
    if (customerInfo.name || customerInfo.email || customerInfo.phone) {
      doc.setFontSize(12);
      doc.setTextColor(0, 0, 0);
      doc.text("Customer Information:", 20, 50);

      doc.setFontSize(10);
      if (customerInfo.name) doc.text(`Name: ${customerInfo.name}`, 20, 60);
      if (customerInfo.email) doc.text(`Email: ${customerInfo.email}`, 20, 65);
      if (customerInfo.phone) doc.text(`Phone: ${customerInfo.phone}`, 20, 70);

      // Add quotation date
      doc.text(`Date: ${new Date().toLocaleDateString()}`, 150, 60);
      doc.text(`Quotation #: QT-${Date.now().toString().substr(-6)}`, 150, 65);
    } else {
      // Continuing frontend/src/utils/pdfGenerator.js
      doc.text(`Date: ${new Date().toLocaleDateString()}`, 150, 50);
      doc.text(`Quotation #: QT-${Date.now().toString().substr(-6)}`, 150, 55);
    }

    // Add quotations
    let yPosition = customerInfo.name ? 85 : 65;

    quotations.forEach((quotation, index) => {
      // Add quotation title
      doc.setFontSize(14);
      doc.setTextColor(0, 0, 0);
      doc.text(`Quotation ${index + 1}`, 20, yPosition);

      // Parse the quotation text
      const lines = quotation.text.split("\n");

      // Extract service details
      let serviceDescription = "";
      let quantity = 1;
      let unitPrice = 0;
      let subtotal = 0;
      let tax = 0;
      let total = 0;

      lines.forEach((line) => {
        if (line.includes("Service Description:")) {
          serviceDescription = line.split("Service Description:")[1].trim();
        } else if (line.includes("Quantity:")) {
          quantity = parseInt(line.split("Quantity:")[1].trim(), 10);
        } else if (line.includes("Unit Price (RM):")) {
          unitPrice = parseFloat(line.split("Unit Price (RM):")[1].trim());
        } else if (line.includes("Subtotal:")) {
          subtotal = parseFloat(line.split("Subtotal:")[1].trim());
        } else if (line.includes("Tax (8%):")) {
          tax = parseFloat(line.split("Tax (8%):")[1].trim());
        } else if (line.includes("Total:")) {
          total = parseFloat(line.split("Total:")[1].trim());
        }
      });

      // Add service details table
      doc.autoTable({
        startY: yPosition + 5,
        head: [
          [
            "Service Description",
            "Quantity",
            "Unit Price (RM)",
            "Subtotal",
            "Tax (8%)",
            "Total",
          ],
        ],
        body: [
          [
            serviceDescription,
            quantity,
            unitPrice.toFixed(2),
            subtotal.toFixed(2),
            tax.toFixed(2),
            total.toFixed(2),
          ],
        ],
        theme: "grid",
        headStyles: { fillColor: [0, 0, 128], textColor: [255, 255, 255] },
        margin: { left: 20, right: 20 },
      });

      // Update Y position for next quotation
      yPosition = doc.lastAutoTable.finalY + 20;

      // Add a new page if needed
      if (yPosition > 250 && index < quotations.length - 1) {
        doc.addPage();
        yPosition = 20;
      }
    });

    // Get the final Y position
    const finalY = doc.lastAutoTable.finalY + 20;

    doc.setFontSize(12);
    doc.setTextColor(0, 0, 0);
    doc.text("Terms and Conditions:", 20, finalY);

    doc.setFontSize(9);
    doc.setTextColor(100, 100, 100);
    const terms = [
      "1. This quotation is valid for 30 days from the date of issue.",
      "2. Payment terms: 50% advance, balance upon completion.",
      "3. Warranty: All services carry a 90-day warranty unless otherwise specified.",
      "4. Additional charges may apply for work outside the scope of this quotation.",
      "5. Cancellation policy: 24-hour notice required to avoid cancellation fees.",
    ];

    terms.forEach((term, index) => {
      doc.text(term, 20, finalY + 10 + index * 5);
    });

    // Add footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(150, 150, 150);
      doc.text(`Page ${i} of ${pageCount}`, 105, 290, { align: "center" });
      doc.text("Generated by Service Quotation System", 105, 295, {
        align: "center",
      });
    }

    return doc;
  } catch (error) {
    console.error("Error generating PDF:", error);
    throw error;
  }
};

export const downloadQuotationPDF = async (quotations, customerInfo = {}) => {
  try {
    // Try client-side generation first
    const doc = generateQuotationPDF(quotations, customerInfo);
    doc.save(`quotation_${Date.now()}.pdf`);
  } catch (error) {
    console.error("Error generating PDF:", error);

    // Show error message to user
    alert(
      "There was an error generating the PDF. Please try the server download option instead."
    );

    // Optionally, try server-side download as fallback
    try {
      if (store && store.getters && store.getters["chat/getSessionId"]) {
        const sessionId = store.getters["chat/getSessionId"];
        await chatService.downloadQuotations(sessionId);
      }
    } catch (serverError) {
      console.error("Server-side PDF generation also failed:", serverError);
    }
  }
};
