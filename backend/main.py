from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
import uvicorn
import chatbot_sqlFinal as chatbot
import traceback
import logging
import re
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import json
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot API", description="API for the chatbot quotation system")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Define request models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ResetRequest(BaseModel):
    session_id: str = "default"

@app.on_event("startup")
async def startup_event():
    """Initialize the chatbot data on startup"""
    try:
        # Initialize the chatbot data
        chatbot.get_quotation_data()
        chatbot.analyze_data()
        logger.info("Chatbot data initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing chatbot data: {e}")
        logger.error(traceback.format_exc())
        # We don't want to crash the app, but log the error

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Process a chat message and return a response"""
    try:
        logger.info(f"Received chat request: {request.message} (session: {request.session_id})")
        
        # Ensure message is a string
        message = str(request.message) if request.message else ""
        session_id = str(request.session_id) if request.session_id else "default"
        
        result = chatbot.process_message(message, session_id)
        logger.info(f"Chat processing result: {result}")
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/reset")
async def reset_chat(request: ResetRequest):
    """Reset a chat session"""
    try:
        logger.info(f"Resetting chat session: {request.session_id}")
        result = chatbot.process_message('reset', request.session_id)
        return JSONResponse(content={"success": True, "message": "Chat session reset"})
    except Exception as e:
        logger.error(f"Error resetting chat session: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/refresh-data")
async def refresh_data():
    """Refresh the data cache"""
    try:
        logger.info("Refreshing data cache")
        message = chatbot.refresh_data()
        return JSONResponse(content={"success": True, "message": message})
    except Exception as e:
        logger.error(f"Error refreshing data: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

def parse_quotation_text(quotation_text: str) -> Dict:
    """Parse quotation text to extract details"""
    lines = quotation_text.split("\n")
    service_description = ""
    quantity = 1
    unit_price = 0.0
    subtotal = 0.0
    tax = 0.0
    total = 0.0
    
    # First, check if this is a multi-line service description
    service_desc_started = False
    service_desc_lines = []
    
    for line in lines:
        line = line.strip()
        if "Service Description:" in line:
            service_desc_started = True
            service_desc_lines.append(line.split("Service Description:")[1].strip())
        elif service_desc_started and not any(key in line for key in ["Quantity:", "Unit Price (RM):", "Subtotal:", "Tax (8%):", "Total:"]):
            # This is a continuation of the service description
            service_desc_lines.append(line)
        elif "Quantity:" in line:
            service_desc_started = False  # End of service description
            try:
                quantity = int(line.split("Quantity:")[1].strip())
            except ValueError:
                pass
        elif "Unit Price (RM):" in line:
            try:
                unit_price = float(line.split("Unit Price (RM):")[1].strip())
            except ValueError:
                pass
        elif "Subtotal:" in line:
            try:
                subtotal = float(line.split("Subtotal:")[1].strip())
            except ValueError:
                pass
        elif "Tax (8%):" in line:
            try:
                tax = float(line.split("Tax (8%):")[1].strip())
            except ValueError:
                pass
        elif "Total:" in line:
            try:
                total = float(line.split("Total:")[1].strip())
            except ValueError:
                pass
    
    # Join the service description lines
    service_description = " ".join(service_desc_lines)
    
    # If we couldn't parse the values properly, try to calculate them
    if subtotal == 0.0 and unit_price > 0 and quantity > 0:
        subtotal = unit_price * quantity
    
    if tax == 0.0 and subtotal > 0:
        tax = subtotal * 0.08  # Assuming 8% tax
    
    if total == 0.0 and subtotal > 0 and tax > 0:
        total = subtotal + tax
    
    return {
        'service_description': service_description,
        'quantity': quantity,
        'unit_price': unit_price,
        'subtotal': subtotal,
        'tax': tax,
        'total': total
    }

def get_quotation_data(context: Dict) -> List[Dict]:
    """Get all quotation data from the context"""
    quotations = []
    seen_descriptions = set()  # Track seen service descriptions
    
    # Check if there are confirmed quotations in the context
    if 'confirmed_quotations' in context:
        for quotation_text in context['confirmed_quotations']:
            quotation_data = parse_quotation_text(quotation_text)
            # Only add if we have a service description and haven't seen it before
            if quotation_data['service_description'] and quotation_data['service_description'] not in seen_descriptions:
                seen_descriptions.add(quotation_data['service_description'])
                quotations.append(quotation_data)
    
    # If no confirmed quotations found in the context's confirmed_quotations list,
    # try to get them from the clean_quotation or last_quotation
    if not quotations:
        # Try to get the clean quotation first
        clean_quotation = context.get('clean_quotation')
        if clean_quotation:
            quotation_data = parse_quotation_text(clean_quotation)
            if quotation_data['service_description'] and quotation_data['service_description'] not in seen_descriptions:
                seen_descriptions.add(quotation_data['service_description'])
                quotations.append(quotation_data)
        else:
            # Fall back to last_quotation if needed
            last_quotation = context.get('last_quotation')
            if last_quotation:
                # Extract just the SERVICE QUOTATION part using regex
                match = re.search(r'(SERVICE QUOTATION\s+--+\s+Service Description:.+?Total: \d+\.\d+)', 
                                last_quotation, re.DOTALL)
                
                if match:
                    quotation_text = match.group(1).strip()
                    quotation_data = parse_quotation_text(quotation_text)
                    if quotation_data['service_description'] and quotation_data['service_description'] not in seen_descriptions:
                        seen_descriptions.add(quotation_data['service_description'])
                        quotations.append(quotation_data)
                else:
                    # Fallback if regex doesn't match
                    quotation_data = parse_quotation_text(last_quotation)
                    if quotation_data['service_description'] and quotation_data['service_description'] not in seen_descriptions:
                        seen_descriptions.add(quotation_data['service_description'])
                        quotations.append(quotation_data)
    
    return quotations

@app.get("/api/quotations/download")
@app.get("/api/quotations/download")
async def download_quotations(
    session_id: str = "default", 
    format: str = "pdf",
    customer_name: str = None,
    customer_email: str = None,
    customer_phone: str = None,
    quotations: str = None
):
    """Download quotations as PDF or TXT"""
    try:
        logger.info(f"Downloading quotations for session: {session_id}")
        
        # Check if the session exists
        if session_id not in chatbot._conversation_context:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get the context from the session
        context = chatbot._conversation_context[session_id]
        
        # Parse quotations from the request if provided
        quotation_data = []
        if quotations:
            try:
                # Parse the JSON string of quotation texts
                quotation_texts = json.loads(quotations)
                
                # Track seen service descriptions to avoid duplicates
                seen_descriptions = set()
                
                for text in quotation_texts:
                    parsed = parse_quotation_text(text)
                    
                    # Only add if we have a service description and haven't seen it before
                    if parsed['service_description'] and parsed['service_description'] not in seen_descriptions:
                        seen_descriptions.add(parsed['service_description'])
                        quotation_data.append(parsed)
                        
                logger.info(f"Successfully parsed {len(quotation_data)} unique quotations from request")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse quotations JSON: {quotations}")
        
        # If no quotations were provided in the request, try to get them from the context
        if not quotation_data:
            quotation_data = get_quotation_data(context)
            logger.info(f"Retrieved {len(quotation_data)} quotations from context")
        
        if not quotation_data:
            logger.warning(f"No quotations found for session: {session_id}")
            raise HTTPException(status_code=404, detail="No quotations found for this session")
        
        # If text format is requested, return as text file
        if format.lower() == "txt":
            # Create a text representation of the quotations
            text_content = ""
            for i, quotation in enumerate(quotation_data):
                if i > 0:
                    text_content += "\n\n" + "-" * 50 + "\n\n"
                
                text_content += f"SERVICE QUOTATION\n"
                text_content += f"------------------------------------------\n"
                text_content += f"Service Description: {quotation['service_description']}\n"
                text_content += f"Quantity: {quotation['quantity']}\n"
                text_content += f"Unit Price (RM): {quotation['unit_price']:.2f}\n"
                text_content += f"Subtotal: {quotation['subtotal']:.2f}\n"
                text_content += f"Tax (8%): {quotation['tax']:.2f}\n"
                text_content += f"Total: {quotation['total']:.2f}\n"
            
            # Create a temporary file
            temp_file = "temp_quotation.txt"
            with open(temp_file, "w") as f:
                f.write(text_content)
            
            logger.info(f"Returning quotation text file for session: {session_id}")
            return FileResponse(
                path=temp_file,
                filename=f"quotation_{session_id}.txt",
                media_type="text/plain"
            )
        
        # Otherwise, generate PDF
        logger.info(f"Generating PDF with {len(quotation_data)} quotations for session: {session_id}")
        
        # Create a PDF in memory
        buffer = io.BytesIO()
        
        # Use A4 page size for more space
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        
        # Add styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            alignment=1,  # Center alignment
            spaceAfter=0.3*inch,
            fontSize=18
        )
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=0.05*inch,  # Reduced spacing
            textColor=colors.navy
        )
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=10,
            leading=14
        )
        company_style = ParagraphStyle(
            'Company',
            parent=styles['Normal'],
            fontSize=10,
            alignment=1,  # Center alignment
            textColor=colors.darkgrey
        )
        section_title_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.navy,
            spaceAfter=0.1*inch,
            spaceBefore=0.2*inch
        )
        
        # Add title
        elements.append(Paragraph("Service Quotation System", title_style))
        
        # Add company details
        elements.append(Paragraph("123 Service Road, Business District", company_style))
        elements.append(Paragraph("Phone: +123-456-7890 | Email: info@servicequotation.com", company_style))
        elements.append(Spacer(1, 0.25*inch))
        
        # Add customer info and date in a combined table
        elements.append(Paragraph("Customer Information:", subtitle_style))
        
        # Combine customer info and date into a single table
        combined_data = []
        if customer_name:
            combined_data.append(["Name:", customer_name])
        if customer_email:
            combined_data.append(["Email:", customer_email])
        if customer_phone:
            combined_data.append(["Phone:", customer_phone])
            
        # Add date and quotation number without a spacer row
        combined_data.append(["Date:", datetime.now().strftime('%Y-%m-%d')])
        combined_data.append(["Quotation:", f"QT-{session_id[-6:]}"])  # Removed # symbol
        
        # Create a table for the combined info with left alignment
        combined_table = Table(combined_data, colWidths=[1.2*inch, 5.3*inch])
        combined_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),  # Even more reduced padding
            ('TOPPADDING', (0, 0), (-1, -1), 2),     # Even more reduced padding
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),      # Left align the labels
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),      # Left align the values
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # No background or line separators
        ]))
        
        # Create a container to hold the table and position it to the left
        table_container = Table([[combined_table]], colWidths=[doc.width])
        table_container.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),  # Left align the inner table
            ('LEFTPADDING', (0, 0), (0, 0), 0), # No left padding
            ('RIGHTPADDING', (0, 0), (0, 0), 0), # No right padding
        ]))
        
        elements.append(table_container)
        elements.append(Spacer(1, 0.2*inch))
        
        # Add a horizontal line to separate header from quotations
        elements.append(Paragraph("<hr/>", normal_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Create a single table for all quotations
        # First, create the header row
        table_data = [["Item", "Service Description", "Quantity", "Unit Price (RM)", "Subtotal", "Tax (8%)", "Total"]]
        
        # Add each quotation as a row in the table
        for i, quotation in enumerate(quotation_data):
            # Create a paragraph for the service description to handle long text better
            service_desc_para = Paragraph(quotation['service_description'], normal_style)
            
            # Add the row to the table (using i+1 instead of f"#{i+1}")
            table_data.append([
                str(i+1),  # Just the number without the # symbol
                service_desc_para,
                str(quotation['quantity']),
                f"{quotation['unit_price']:.2f}",
                f"{quotation['subtotal']:.2f}",
                f"{quotation['tax']:.2f}",
                f"{quotation['total']:.2f}"
            ])
        
        # Calculate column widths
        available_width = doc.width - doc.leftMargin - doc.rightMargin
        col_widths = [
            available_width * 0.1,  # item 
            available_width * 0.40,  # Service Description 
            available_width * 0.12,  # Quantity 
            available_width * 0.18,  # Unit Price 
            available_width * 0.12,  # Subtotal 
            available_width * 0.11,  # Tax 
            available_width * 0.12   # Total 
        ]
        
        # Create the table
        quotations_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style the table
        table_style = TableStyle([
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),  # White background for header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Data row styling - white background
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # White background for all data rows
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Center align item number
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Left align service description
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'), # Center align other columns
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), # Vertical alignment
            
            # Grid styling
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            
            # Add padding for better readability
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
            
            # Word wrapping for service description
            ('WORDWRAP', (1, 1), (1, -1), True),
        ])
        
        quotations_table.setStyle(table_style)
        elements.append(quotations_table)
        
        # Calculate total amount for all quotations
        if len(quotation_data) > 1:
            elements.append(Spacer(1, 0.4*inch))
            
            total_amount = sum(q['total'] for q in quotation_data)
            
            # Add summary table
            summary_data = [
                ["Total Quotations", "Total Amount (RM)"],
                [str(len(quotation_data)), f"{total_amount:.2f}"]
            ]
            
            summary_table = Table(summary_data, colWidths=[4*inch, 4*inch])
            summary_style = TableStyle([
                # Header row styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.white),  # White background
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                
                # Data row styling - white background
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # White background
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                
                # Grid styling
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BOX', (0, 0), (-1, -1), 1, colors.black),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
                
                # Add padding
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ])
            
            summary_table.setStyle(summary_style)
            elements.append(summary_table)
        
        elements.append(Spacer(1, 0.5*inch))
        elements.append(Paragraph("<hr/>", normal_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Add terms and conditions
        elements.append(Paragraph("Terms and Conditions", section_title_style))
        terms = [
            ["1.", "This quotation is valid for 30 days from the date of issue."],
            ["2.", "Payment terms: 50% advance, balance upon completion."],
            ["3.", "Warranty: All services carry a 90-day warranty unless otherwise specified."],
            ["4.", "Additional charges may apply for work outside the scope of this quotation."],
            ["5.", "Cancellation policy: 24-hour notice required to avoid cancellation fees."]
        ]
        
        terms_table = Table(terms, colWidths=[0.3*inch, 7*inch])
        terms_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(terms_table)
        
        # Add a note about taxes
        elements.append(Spacer(1, 0.3*inch))
        tax_note = Paragraph("Note: All prices are subject to 8% tax as shown in the quotation.", 
                            ParagraphStyle(
                                'Note',
                                parent=normal_style,
                                fontSize=8,
                                textColor=colors.grey
                            ))
        elements.append(tax_note)
        
        # Add footer
        def add_page_number(canvas, doc):
            canvas.saveState()
            
            # Add a line at the bottom of each page
            canvas.setStrokeColor(colors.lightgrey)
            canvas.line(doc.leftMargin, 0.7*inch, doc.width + doc.leftMargin, 0.7*inch)
            
            # Add page number
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.grey)
            page_num = f"Page {canvas.getPageNumber()}"
            canvas.drawRightString(doc.width + doc.leftMargin, 0.4*inch, page_num)
            
            # Add company info in footer
            canvas.setFont('Helvetica', 8)
            canvas.drawCentredString(doc.width/2 + doc.leftMargin, 0.4*inch, 
                                    "Generated by Service Quotation System | www.servicequotation.com")
            
            # Add date in footer
            canvas.drawString(doc.leftMargin, 0.4*inch, 
                            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            
            canvas.restoreState()
        
        # Build the PDF with page numbers
        doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
        
        # Return the PDF
        buffer.seek(0)
        return StreamingResponse(
            buffer, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=quotation_{session_id}.pdf"}
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error downloading quotations: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
        
    
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

if __name__ == "__main__":
    # Run the FastAPI app with uvicorn 
    uvicorn.run(app, host="0.0.0.0", port=5000)