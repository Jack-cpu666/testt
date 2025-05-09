import os
import logging
from flask import Flask, request, jsonify, redirect, url_for, Response

from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.models.order_request import OrderRequest
from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest
from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown
from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent
from paypalserversdk.api_helper import ApiHelper

app = Flask(__name__)
# For Render, set a strong FLASK_SECRET_KEY as an environment variable
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'this_is_a_default_unsafe_secret_for_testing_only')

# --- DANGER: LIVE Credentials for Testing ONLY ---
# REPLACE THE PLACEHOLDERS BELOW WITH YOUR ACTUAL LIVE CREDENTIALS
# BEFORE DEPLOYING THIS TEST APP.
PAYPAL_LIVE_CLIENT_ID = "AcmlO6PwqeILCKfPYKY-c4rapIApzXQJngzmYHPJjkVvIIWU0n4voHw_2mk0LTE7O6xf9247-SS3cc5s"
PAYPAL_LIVE_CLIENT_SECRET = "EDFnMBY8LzfvtDC2c3QuvO0GipPELvXakSgdmsxeTkis1gBFswtPgHzSE4dI83RIoFEUWPzs1AHBpuh4"
# --- End of DANGER section ---

# Your Provided LIVE Credentials (to be used in the placeholders above):
# Client ID: AcmlO6PwqeILCKfPYKY-c4rapIApzXQJngzmYHPJjkVvIIWU0n4voHw_2mk0LTE7O6xf9247-SS3cc5s
# Secret: EDFnMBY8LzfvtDC2c3QuvO0GipPELvXakSgdmsxeTkis1gBFswtPgHzSE4dI83RIoFEUWPzs1AHBpuh4

orders_controller = None
paypal_sdk_initialized = False

if PAYPAL_LIVE_CLIENT_ID and PAYPAL_LIVE_CLIENT_ID != "YOUR_LIVE_CLIENT_ID_REPLACE_ME" and \
   PAYPAL_LIVE_CLIENT_SECRET and PAYPAL_LIVE_CLIENT_SECRET != "YOUR_LIVE_CLIENT_SECRET_REPLACE_ME":
    try:
        paypal_client = PaypalServersdkClient(
            client_credentials_auth_credentials=ClientCredentialsAuthCredentials(
                o_auth_client_id=PAYPAL_LIVE_CLIENT_ID,
                o_auth_client_secret=PAYPAL_LIVE_CLIENT_SECRET
            )
            # No explicit logging for this minimal test app
        )
        orders_controller = paypal_client.orders
        paypal_sdk_initialized = True
        logging.info("PayPal SDK Client initialized successfully for LIVE (Simple Test App).")
    except Exception as e:
        logging.error(f"Failed to initialize PayPal SDK Client (Simple Test App): {e}")
else:
    logging.error("FATAL: PayPal Live Client ID and/or Secret placeholders not replaced in app.py.")


INDEX_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PayPal 1 Cent Test (LIVE)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: sans-serif; padding: 20px; background-color: #f4f4f4; }}
        .container {{ background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); max-width: 500px; margin: auto; }}
        h1 {{ color: #333; }}
        strong {{ color: red; }}
        #paypal-button-container {{ margin-top: 20px; }}
        #payment-status {{ margin-top:15px; font-weight: bold; }}
        .error {{ color: red; }}
        .success {{ color: green; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PayPal 1 Cent Charge Test (LIVE)</h1>
        <p>This will attempt to charge $0.01 USD using your LIVE PayPal credentials.</p>
        <p><strong>Warning:</strong> This uses LIVE credentials. This is for a specific, isolated test. Delete this app and consider rotating keys after testing.</p>

        <div id="paypal-button-container"></div>
        <p id="payment-status"></p>
        <a href="/">Try Again / Home</a>
    </div>

    <script src="https://www.paypal.com/sdk/js?client-id={client_id}¤cy=USD"></script>
    <script>
        const paymentStatusEl = document.getElementById('payment-status');
        const paypalButtonContainer = document.getElementById('paypal-button-container');
        const clientIdFromTemplate = "{client_id}";

        if (!clientIdFromTemplate || clientIdFromTemplate === "YOUR_LIVE_CLIENT_ID_REPLACE_ME") {{
            paymentStatusEl.textContent = 'Error: PayPal Client ID not configured correctly in the HTML template.';
            paymentStatusEl.className = 'error';
            if (paypalButtonContainer) paypalButtonContainer.style.display = 'none';
        }} else if (!{sdk_ready}) {{
            paymentStatusEl.textContent = 'Error: PayPal SDK could not be initialized on the server. Check server logs and credentials.';
            paymentStatusEl.className = 'error';
            if (paypalButtonContainer) paypalButtonContainer.style.display = 'none';
        }}
        else {{
            paypal.Buttons({{
                createOrder: function(data, actions) {{
                    paymentStatusEl.textContent = 'Creating order...';
                    paymentStatusEl.className = '';
                    return fetch('/create_order', {{
                        method: 'POST'
                    }})
                    .then(res => {{
                        if (!res.ok) {{
                            return res.json().then(errData => {{
                                const errMsg = (errData && errData.error) ? errData.error : 'Server error during order creation.';
                                throw new Error(errMsg);
                            }});
                        }}
                        return res.json();
                    }})
                    .then(order => {{
                        if (order && order.id) {{
                            paymentStatusEl.textContent = 'Order created (' + order.id + '). Redirecting to PayPal...';
                            return order.id;
                        }} else {{
                            const errMsg = (order && order.error) ? order.error : 'Could not get order ID from server.';
                            throw new Error(errMsg);
                        }}
                    }})
                    .catch(err => {{
                        console.error('Create Order Error:', err);
                        paymentStatusEl.textContent = 'Error creating order: ' + err.message;
                        paymentStatusEl.className = 'error';
                        throw err;
                    }});
                }},
                onApprove: function(data, actions) {{
                    paymentStatusEl.textContent = 'Payment approved. Capturing payment...';
                    paymentStatusEl.className = '';
                    return fetch(`/capture_order/${{data.orderID}}`, {{
                        method: 'POST'
                    }})
                    .then(res => {{
                         if (!res.ok) {{
                            return res.json().then(errData => {{
                                const errMsg = (errData && errData.error) ? errData.error : 'Server error during payment capture.';
                                throw new Error(errMsg);
                            }});
                        }}
                        return res.json();
                    }})
                    .then(details => {{
                        if (details && details.id && details.status === 'COMPLETED') {{
                            paymentStatusEl.textContent = 'Payment successful! Order ID: ' + details.id + ', Status: ' + details.status;
                            paymentStatusEl.className = 'success';
                            window.location.href = `/success?orderID=${{details.id}}`;
                        }} else {{
                            const errMsg = (details && details.error) ? details.error : `Payment status not completed: ${(details && details.status)}`;
                            paymentStatusEl.textContent = 'Capture issue: ' + errMsg;
                            paymentStatusEl.className = 'error';
                             window.location.href = `/cancel?orderID=${{data.orderID}}&error=capture_not_completed&status=${{(details ? details.status : 'unknown')}}`;
                        }}
                    }})
                    .catch(err => {{
                        console.error('Capture Order Error:', err);
                        paymentStatusEl.textContent = 'Error capturing payment: ' + err.message;
                        paymentStatusEl.className = 'error';
                        window.location.href = `/cancel?orderID=${{data.orderID}}&error=capture_failed_exception`;
                    }});
                }},
                onCancel: function(data) {{
                    paymentStatusEl.textContent = 'Payment cancelled by user. Order ID: ' + data.orderID;
                    paymentStatusEl.className = 'error';
                    window.location.href = `/cancel?orderID=${{data.orderID}}`;
                }},
                onError: function(err) {{
                    console.error('PayPal SDK Error:', err);
                    paymentStatusEl.textContent = 'PayPal SDK Error: ' + (err.message || 'An unknown PayPal error occurred.');
                    paymentStatusEl.className = 'error';
                }}
            }}).render('#paypal-button-container');
        }}
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    if not PAYPAL_LIVE_CLIENT_ID or PAYPAL_LIVE_CLIENT_ID == "YOUR_LIVE_CLIENT_ID_REPLACE_ME":
        return "<h1>Configuration Error</h1><p>PayPal Client ID placeholder not replaced in server code. Please update app.py.</p>", 500
    # Pass sdk_ready status to template
    return Response(INDEX_HTML_TEMPLATE.format(client_id=PAYPAL_LIVE_CLIENT_ID, sdk_ready=str(paypal_sdk_initialized).lower()), mimetype='text/html')

@app.route('/create_order', methods=['POST'])
def create_order_api():
    if not orders_controller:
        return jsonify({"error": "PayPal SDK not initialized on server. Check credentials in app.py and server logs."}), 503

    order_request = OrderRequest(
        intent=CheckoutPaymentIntent.CAPTURE,
        purchase_units=[
            PurchaseUnitRequest(
                amount=AmountWithBreakdown(currency_code="USD", value="0.01"), # 1 cent
                description="Test 1 Cent Charge (LIVE)"
            )
        ],
        application_context={
            "return_url": url_for('success_page', _external=True),
            "cancel_url": url_for('cancel_page', _external=True),
            "brand_name": "Live Test App",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW"
        }
    )
    try:
        response = orders_controller.create_order({'body': order_request})
        if response.body and hasattr(response.body, 'id'):
            return jsonify({"id": response.body.id})
        else:
            err_details = ApiHelper.json_serialize(response.body) if response.body else 'No Body from PayPal'
            logging.error(f"Create order response invalid: Status {response.status_code}, Body: {err_details}")
            return jsonify({"error": f"Failed to create order or get ID from PayPal. Details: {err_details}"}), 500
    except ApiException as e:
        logging.error(f"PayPal API Exception during order creation: Code: {e.status_code if hasattr(e, 'status_code') else 'N/A'}, Message: {str(e)}")
        return jsonify({"error": f"PayPal API Error: {str(e)}"}), e.status_code if hasattr(e, 'status_code') else 500
    except Exception as e:
        logging.error(f"General Exception during order creation: {e}", exc_info=True)
        return jsonify({"error": f"Server Error during order creation: {str(e)}"}), 500

@app.route('/capture_order/<order_id>', methods=['POST'])
def capture_order_api(order_id):
    if not orders_controller:
        return jsonify({"error": "PayPal SDK not initialized on server. Check credentials in app.py and server logs."}), 503
    try:
        # The SDK expects a dictionary with 'id' for named path parameters
        response = orders_controller.capture_order({"id": order_id})
        if response.body and hasattr(response.body, 'id') and hasattr(response.body, 'status'):
             return jsonify({
                "id": response.body.id,
                "status": response.body.status,
                "full_details_for_debug": ApiHelper.json_serialize(response.body)
            })
        else:
            err_details = ApiHelper.json_serialize(response.body) if response.body else 'No Body from PayPal'
            logging.error(f"Capture order response invalid for {order_id}: Status {response.status_code}, Body: {err_details}")
            return jsonify({"error": f"Failed to capture payment or get valid details from PayPal. Details: {err_details}"}), 500
    except ApiException as e:
        logging.error(f"PayPal API Exception during order capture ({order_id}): Code: {e.status_code if hasattr(e, 'status_code') else 'N/A'}, Message: {str(e)}")
        return jsonify({"error": f"PayPal API Error: {str(e)}"}), e.status_code if hasattr(e, 'status_code') else 500
    except Exception as e:
        logging.error(f"General Exception during order capture ({order_id}): {e}", exc_info=True)
        return jsonify({"error": f"Server Error during payment capture: {str(e)}"}), 500

@app.route('/success')
def success_page():
    order_id = request.args.get('orderID', 'N/A')
    return f"<h1>Payment Successful!</h1><p>Order ID: {order_id}</p><p><a href='/'>Test Again</a></p>"

@app.route('/cancel')
def cancel_page():
    order_id = request.args.get('orderID', 'N/A')
    error_msg = request.args.get('error', 'User cancelled or payment failed.')
    status_msg = request.args.get('status', '')
    return f"<h1>Payment Cancelled or Failed</h1><p>Order ID: {order_id}</p><p>Reason: {error_msg}</p><p>Status: {status_msg}</p><p><a href='/'>Test Again</a></p>"

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    port = int(os.environ.get('PORT', 5002)) # Render sets PORT
    # For production on Render, FLASK_ENV=production is set, making debug False
    is_production = os.environ.get("FLASK_ENV", "").lower() == "production"
    app.run(host='0.0.0.0', port=port, debug=not is_production)
