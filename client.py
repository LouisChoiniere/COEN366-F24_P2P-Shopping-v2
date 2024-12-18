import socket
import random
import threading
import time

input_lock = threading.Lock()
out_lock = threading.Lock()


def generate_rq():
    return f"RQ{random.randint(1000, 9999)}"

def start_client():
    global registered
    with input_lock:

        server_ip = input("Enter the server IP address: ")
        server_port = 5000
        buffer_size = 1024

        client_ip = socket.gethostbyname(socket.gethostname())

        client_name = ""
        client_udp_port = ""
        client_tcp_port = ""
        c_socket = None
        pending_search_requests = {}
        pending_negotiations = {}
        pending_reservations = {}
        registered = False
        transaction_flag = threading.Event()

    def show_menu(registered):
        with out_lock:
            print("\n=== Commands ===")
            if not registered:
                print("register  (r) - Register with the server")
            else:
                print("deregister(d) - Deregister from the server")
                print("search    (s) <item_name> <description> <max_price> - Search for an item")
                print("offer     (o) <rq> <item_name> <price> - Offer an item in response to a search request")
                print("accept    (a) <rq> - Accept the negotiated price offered by the buyer")
                print("refuse    (f) <rq> - Refuse the negotiated price offered by the buyer")
                print("buy       (b) <rq> - Buy an item at the reserved price")
                print("sell      (y) <rq> - Sell an item at the reserved price")
                print("cancel    (c) <rq> - Cancel the reservation for an item")
                print("help      (h) - Show this help message")
                print("quit      (q) - Exit the client\n")

    def listen_for_messages():
        """Continuously listen for incoming messages from the server."""
        while True:
            response, server_address = c_socket.recvfrom(buffer_size)
            response = response.decode()
            print(f"\nReceived message from server: {response}\nEnter command:")

            parts = response.split()
            if not parts:
                continue

            command = parts[0]

            if command == "SEARCH":
                rq = parts[1]
                item_name = parts[2]
                description = parts[3]
                print(f"\nServer is searching for: {item_name} (Description: {description})")
                pending_search_requests[rq] = (item_name, description)

            elif command == "NEGOTIATE":
                rq = parts[1]
                item_name = parts[2]
                max_price = parts[3]
                print(f"\nNegotiation request received for {item_name} with max price {max_price}")
                pending_negotiations[rq] = (item_name, max_price)

            elif command == "FOUND":
                rq = parts[1]
                item_name = parts[2]
                price = parts[3]
                print(
                    f"\nFOUND: The item '{item_name}' is available at price {price}. You may proceed with the purchase.")
                pending_reservations[rq] = (item_name, price)

            elif command == "NOT_FOUND":
                rq = parts[1]
                item_name = parts[2]
                max_price = parts[3]
                print(f"\nNOT_FOUND: The item '{item_name}' is not available at the max price {max_price}.")

            elif command == "RESERVE":
                rq = parts[1]
                item_name = parts[2]
                price = parts[3]
                print(f"\nRESERVE: You have reserved the item '{item_name}' at price {price}. Awaiting buyer's action.")
                pending_reservations[rq] = (item_name, price)

    def start_tcp_listener():
        """Start a TCP server to handle incoming messages from the server."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.bind((client_ip, int(client_tcp_port)))
            tcp_socket.listen(5)
            print(f"TCP listener started on {client_ip}:{client_tcp_port}")

            while True:
                conn, addr = tcp_socket.accept()
                threading.Thread(target=handle_tcp_transaction, args=(conn,), daemon=True).start()

    def handle_tcp_transaction(conn):
        """Handle incoming TCP messages."""
        try:
            message = conn.recv(buffer_size).decode()
            if message.startswith("INFORM_Req"):

                transaction_flag.set()
                # Parse the INFORM_Req message
                parts = message.split()
                rq = parts[1]
                item_name = parts[2]
                price = parts[3]

                print(f"\nTransaction request received for {item_name} at {price}.")

                # Collect all required transaction information
                print("Enter transaction details:")
                cc_number = input(" - Credit card number: ").strip()

                cc_expiry = input(" - Expiry date (MM/YY or MMYY): ").strip()
                if len(cc_expiry) == 4 and cc_expiry.isdigit():
                    cc_expiry = f"{cc_expiry[:2]}/{cc_expiry[2:]}"  # Normalize MMYY to MM/YY

                address = input(" - Address: ").strip()

                # Send INFORM_Res response
                response = f"INFORM_Res {rq} {client_name} {cc_number} {cc_expiry} {address}"
                conn.sendall(response.encode())

                print("Transaction information sent to the server.")

                transaction_flag.clear()
            elif message.startswith("Shipping_Info"):

                parts = message.split()
                item_name = parts[2]
                address = parts[3]

                print(f"\nShipping address for the buyer is: {address}")

        except Exception as e:
            print(f"Error handling TCP transaction: {e}")
        finally:
            conn.close()

    def register():
        nonlocal client_name, client_udp_port, client_tcp_port, c_socket
        global registered

        while not registered:
            print("\n=== Registration ===")
            client_name = input("Enter your name: ")

            client_udp_port = random.randint(5500, 9999)
            client_tcp_port = random.randint(5500, 9999)
            print(f"Auto-generated UDP port: {client_udp_port}")
            print(f"Auto-generated TCP port: {client_tcp_port}")
            rq = generate_rq()

            # Initialize the UDP socket
            c_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            c_socket.bind((client_ip, int(client_udp_port)))  # Bind to the provided UDP port

            # Send registration message to server
            message = f"REGISTER {rq} {client_name} {client_ip} {client_udp_port} {client_tcp_port}"
            c_socket.sendto(message.encode(), (server_ip, server_port))

            # Receive response from the server
            response, server_address = c_socket.recvfrom(buffer_size)
            response_message = response.decode()
            print(f"Server response: {response_message}")

            if "REGISTERED" in response_message:
                # Registration successful
                registered = True
                print("Registration successful.")
                # Start the listener threads
                listener_thread = threading.Thread(target=listen_for_messages, daemon=True)
                listener_thread.start()

                tcp_listener_thread = threading.Thread(target=start_tcp_listener, daemon=True)
                tcp_listener_thread.start()
                return True  # Exit loop and indicate success
            elif "REGISTER-DENIED" in response_message:
                # Registration denied
                print("Registration denied. User already exists. Please try again.")
                print("Hint: Choose a unique name or different port numbers.")
                c_socket.close()  # Close the current socket to allow re-registration
                continue  # Restart the registration loop

    def deregister():
        global registered
        if not client_name:
            print("You must register before deregistering.")
            return
        rq = generate_rq()
        message = f"DE-REGISTER {rq} {client_name}"
        c_socket.sendto(message.encode(), (server_ip, server_port))

        response, server_address = c_socket.recvfrom(buffer_size)
        print(f"Server response: {response.decode()}")
        if "DE-REGISTERED" in response.decode():
            registered = False

    def looking_for():
        if not client_name:
            print("You must register before searching for items.")
            return

        item_name = input("Enter item name: ")
        description = input("Enter item description: ")
        max_price = input("Enter maximum price: ")
        rq = generate_rq()

        message = f"LOOKING_FOR {rq} {client_name} {item_name} {description} {max_price}"
        c_socket.sendto(message.encode(), (server_ip, server_port))
        print("Sent item search request to server.")

    def offer_item():
        if not pending_search_requests:
            print("No pending search requests to offer.")
            return

        rq = input("Enter the request number (RQ#) of the search request to respond to: ")
        if rq not in pending_search_requests:
            print("Invalid request number.")
            return

        item_name, description = pending_search_requests[rq]
        price = input(f"Enter your offer price for {item_name} (Description: {description}): ")

        offer_message = f"OFFER {rq} {client_name} {item_name} {price}"
        c_socket.sendto(offer_message.encode(), (server_ip, server_port))
        print(f"Sent OFFER for {item_name} with price {price}")

        del pending_search_requests[rq]

    def accept_negotiation():
        if not pending_negotiations:
            print("No pending negotiations to accept.")
            return

        rq = input("Enter the request number (RQ#) of the negotiation to accept: ")
        if rq not in pending_negotiations:
            print("Invalid request number.")
            return

        item_name, max_price = pending_negotiations[rq]
        accept_message = f"ACCEPT {rq} {client_name} {item_name} {max_price}"
        c_socket.sendto(accept_message.encode(), (server_ip, server_port))
        print(f"Sent ACCEPT for {item_name} at negotiated price {max_price}")

        del pending_negotiations[rq]

    def refuse_negotiation():
        if not pending_negotiations:
            print("No pending negotiations to refuse.")
            return

        rq = input("Enter the request number (RQ#) of the negotiation to refuse: ")
        if rq not in pending_negotiations:
            print("Invalid request number.")
            return

        item_name, max_price = pending_negotiations[rq]
        refuse_message = f"REFUSE {rq} {client_name} {item_name} {max_price}"
        c_socket.sendto(refuse_message.encode(), (server_ip, server_port))
        print(f"Sent REFUSE for {item_name} at negotiated price {max_price}")

        del pending_negotiations[rq]

    def buy_item():
        """buyer can confirm the buy"""
        if not pending_reservations:
            print("No pending reservations to buy.")
            return

        rq = input("Enter the request number (RQ#) of the reservation to buy: ")
        if rq not in pending_reservations:
            print("Invalid request number.")
            return

        item_name, price = pending_reservations[rq]
        buy_message = f"BUY {rq} {client_name} {item_name} {price}"
        c_socket.sendto(buy_message.encode(), (server_ip, server_port))
        print(f"Sent BUY for {item_name} at price {price}")

        transaction_flag.set()
        time.sleep(10)

        del pending_reservations[rq]

    def sell_item():
        pass

    def cancel_reservation():
        if not pending_reservations:
            print("No pending reservations to cancel.")
            return

        rq = input("Enter the request number (RQ#) of the reservation to cancel: ")
        if rq not in pending_reservations:
            print("Invalid request number.")
            return

        item_name, price = pending_reservations[rq]
        cancel_message = f"CANCEL {rq} {client_name} {item_name} {price}"
        c_socket.sendto(cancel_message.encode(), (server_ip, server_port))
        print(f"Sent CANCEL for {item_name} at price {price}")

        del pending_reservations[rq]

    def handle_command(command, registered):
        if not registered and command in ["register", "r"]:
            register()
            return True
        elif not registered:
            print("You must register first.")
            return False
        else:
            if command in ["deregister", "d"]:
                deregister()
                return False
            elif command in ["search", "s"]:
                looking_for()
            elif command in ["offer", "o"]:
                offer_item()
            elif command in ["accept", "a"]:
                accept_negotiation()
            elif command in ["refuse", "f"]:
                refuse_negotiation()
            elif command in ["buy", "b"]:
                buy_item()
            elif command in ["sell", "y"]:
                sell_item()
            elif command.startswith("cancel") or command.startswith("c"):
                cancel_reservation()
            elif command == "help" or command == "h":
                show_menu()
            elif command == "quit" or command == "q":
                print("Exiting client.")
                return False

            return registered

    def main_loop(busy):
        global registered

        while True:
            if not busy.is_set():
                show_menu(registered)

                with input_lock:
                    command = input("Enter command: ").strip().lower()
                    registered = handle_command(command, registered)
                    if command == "quit" or command == "q":
                        print("Exiting client.")
                        break

        # if c_socket:
        #     c_socket.close()

    threading.Thread(target=main_loop, args=[transaction_flag, ], daemon=False).start()


if __name__ == "__main__":
    start_client()
