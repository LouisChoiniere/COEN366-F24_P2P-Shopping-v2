import socket
import random
import threading


def generate_rq():
    """Generate a random request number."""
    return f"RQ{random.randint(1000, 9999)}"


def start_client():
    # Prompt for the server IP address
    server_ip = input("Enter the server IP address: ")
    server_port = 5000
    buffer_size = 1024

    # Allow manual or automatic detection of the client IP
    client_ip = input("Enter your IP address (leave blank to auto-detect): ")
    if not client_ip:
        # Automatically detect the client's IP address
        client_ip = socket.gethostbyname(socket.gethostname())
        print(f"Automatically detected client IP: {client_ip}")
    else:
        print(f"Using manually entered client IP: {client_ip}")

    client_name = ""
    client_udp_port = ""
    client_tcp_port = ""
    c_socket = None
    pending_search_requests = {}
    pending_negotiations = {}
    pending_reservations = {}

    def show_menu():
        print("\n=== P2P Client Commands ===")
        print("register  (r) - Register with the server")
        print("deregister(d) - Deregister from the server")
        print("search    (s) <item_name> <description> <max_price> - Search for an item")
        print("offer     (o) <rq> <item_name> <price> - Offer an item in response to a search request")
        print("accept    (a) <rq> - Accept the negotiated price offered by the buyer")
        print("refuse    (f) <rq> - Refuse the negotiated price offered by the buyer")
        print("buy       (b) <rq> - Buy an item at the reserved price")
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

            # Handle SEARCH message
            if command == "SEARCH":
                rq = parts[1]
                item_name = parts[2]
                description = parts[3]
                print(f"\nServer is searching for: {item_name} (Description: {description})")
                pending_search_requests[rq] = (item_name, description)

            # Handle NEGOTIATE message
            elif command == "NEGOTIATE":
                rq = parts[1]
                item_name = parts[2]
                max_price = parts[3]
                print(f"\nNegotiation request received for {item_name} with max price {max_price}")
                pending_negotiations[rq] = (item_name, max_price)

            # Handle FOUND message
            elif command == "FOUND":
                rq = parts[1]
                item_name = parts[2]
                price = parts[3]
                print(f"\nFOUND: The item '{item_name}' is available at price {price}. You may proceed with the purchase.")
                pending_reservations[rq] = (item_name, price)

            # Handle NOT_FOUND message
            elif command == "NOT_FOUND":
                rq = parts[1]
                item_name = parts[2]
                max_price = parts[3]
                print(f"\nNOT_FOUND: The item '{item_name}' is not available at the max price {max_price}.")

            # Handle RESERVE message
            elif command == "RESERVE":
                rq = parts[1]
                item_name = parts[2]
                price = parts[3]
                print(f"\nRESERVE: You have reserved the item '{item_name}' at price {price}. Awaiting buyer's action.")
                pending_reservations[rq] = (item_name, price)

    def register():
        nonlocal client_name, client_udp_port, client_tcp_port, c_socket

        client_name = input("Enter your name: ")
        client_udp_port = input("Enter your UDP port number: ")
        client_tcp_port = input("Enter your TCP port number: ")
        rq = generate_rq()

        # Initialize the UDP socket
        c_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        c_socket.bind((client_ip, int(client_udp_port)))  # Use client_ip here

        # Send registration message to server in the correct format
        message = f"REGISTER {rq} {client_name} {client_ip} {client_udp_port} {client_tcp_port}"
        c_socket.sendto(message.encode(), (server_ip, server_port))

        # Receive response from the server
        response, server_address = c_socket.recvfrom(buffer_size)
        print(f"Server response: {response.decode()}")

        # Start the listener thread only after registration is successful
        listener_thread = threading.Thread(target=listen_for_messages, daemon=True)
        listener_thread.start()

    def deregister():
        if not client_name:
            print("You must register before deregistering.")
            return

        rq = generate_rq()
        message = f"DE-REGISTER {rq} {client_name}"
        c_socket.sendto(message.encode(), (server_ip, server_port))

        response, server_address = c_socket.recvfrom(buffer_size)
        print(f"Server response: {response.decode()}")

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
        """Allow the user to respond to a SEARCH request with an OFFER."""
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
        """Allow the user to accept a negotiation request from the server."""
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
        """Allow the user to refuse a negotiation request from the server."""
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
        """Allow the buyer to confirm the purchase of a reserved item."""
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

        del pending_reservations[rq]

    def cancel_reservation():
        """Allow the buyer to cancel a reservation."""
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

    def handle_command(command):
        if command in ["register", "r"]:
            register()
        elif command in ["deregister", "d"]:
            deregister()
        elif command.startswith("search") or command.startswith("s"):
            looking_for()
        elif command.startswith("offer") or command.startswith("o"):
            offer_item()
        elif command.startswith("accept") or command.startswith("a"):
            accept_negotiation()
        elif command.startswith("refuse") or command.startswith("f"):
            refuse_negotiation()
        elif command.startswith("buy") or command.startswith("b"):
            buy_item()
        elif command.startswith("cancel") or command.startswith("c"):
            cancel_reservation()
        elif command == "help" or command == "h":
            show_menu()
        elif command == "quit" or command == "q":
            print("Exiting client.")
            return False
        else:
            print("Unknown command. Type 'help' or 'h' for available commands.")
        return True

    show_menu()
    while True:
        command = input("Enter command: ").strip().lower()
        if not handle_command(command):
            break

    if c_socket:
        c_socket.close()


if __name__ == "__main__":
    start_client()
