import socket
import threading
import time
import json
import os

class Client:
    def __init__(self, name, ip, udp_port, tcp_port):
        self.name = name
        self.ip = ip
        self.udp_port = udp_port
        self.tcp_port = tcp_port

    def to_dict(self):
        return {
            "name": self.name,
            "ip": self.ip,
            "udp_port": self.udp_port,
            "tcp_port": self.tcp_port,
        }

    def from_dict(data):
        return Client(data["name"], data["ip"], data["udp_port"], data["tcp_port"])

def start_server():
    server_ip = "0.0.0.0"
    udp_port = 5000
    tcp_port = 5001
    buffer_size = 1024
    data_file = "server_data.json"
    all_clients = {}
    active_searches = {}
    reservations = {}

    def load_data():
        if os.path.exists(data_file):
            with open(data_file, "r") as file:
                data = json.load(file)
                # Load clients
                for client_name, client_data in data.get("all_clients", {}).items():
                    all_clients[client_name] = Client.from_dict(client_data)
                # Load active searches
                global active_searches
                active_searches = data.get("active_searches", {})
                # Load reservations
                global reservations
                reservations = data.get("reservations", {})
            print("Data loaded from file.")
        else:
            print("No previous data file found. Starting fresh.")

    def save_data():
        data = {
            "all_clients": {name: client.to_dict() for name, client in all_clients.items()},
            "active_searches": active_searches,
            "reservations": reservations,
        }
        with open(data_file, "w") as file:
            json.dump(data, file, indent=4)
        print("Data saved to file.")

    def log_action(action):
        """Log server actions to a log file."""
        with open("server.log", "a") as log_file:
            log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {action}\n")

    def broadcast_search(rq, requester_name, item_name, description, max_price):
        """Send SEARCH message to all clients except the requester."""
        global udp_socket
        num_sellers = 0
        for client_key, client in all_clients.items():
            if client.name != requester_name:
                search_message = f"SEARCH {rq} {item_name} {description}"
                udp_socket.sendto(search_message.encode(), (client.ip, int(client.udp_port)))
                print(f"Sent SEARCH to {client.name} at {client.ip}:{client.udp_port}")
                num_sellers += 1

        active_searches[rq] = {
            "requester_name": requester_name,
            "item_name": item_name,
            "max_price": int(max_price),
            "offers": [],
            "expected_offers": num_sellers
        }

        threading.Thread(target=check_offers_after_timeout, args=(rq,), daemon=True).start()
        log_action(f"SEARCH broadcasted for {item_name} by {requester_name}")
        save_data()
    def check_offers_after_timeout(rq):
        """Evaluate offers after waiting for 5 minutes or receiving all expected offers."""
        global udp_socket
        timeout = 60
        start_time = time.time()

        while time.time() - start_time < timeout:
            if rq not in active_searches:
                return  # The request has already been processed

            if len(active_searches[rq]["offers"]) >= active_searches[rq]["expected_offers"]:
                break

            time.sleep(1)

        if rq in active_searches:
            process_offers(rq)

    def process_offers(rq):
        """Process offers for a request after all responses or timeout."""
        global udp_socket,reservations
        if rq not in active_searches:
            print(f"ERROR: {rq} already removed from active_searches in process_offers.")
            return

        search_info = active_searches[rq]
        buyer_name = search_info["requester_name"]
        max_price = search_info["max_price"]
        offers = search_info["offers"]

        # Filter offers that are within the max price
        valid_offers = [offer for offer in offers if offer[2] <= max_price]

        if valid_offers:
            # Find the offer with the lowest price
            lowest_offer = min(valid_offers, key=lambda x: x[2])
            seller_name, item_name, price = lowest_offer

            # Send RESERVE to seller and FOUND to buyer
            seller_client = all_clients[seller_name]
            reserve_message = f"RESERVE {rq} {item_name} {price}"
            udp_socket.sendto(reserve_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
            print(f"Sent RESERVE to {seller_name} for item {item_name} at price {price}")

            # Notify the buyer about the availability
            buyer_client = all_clients[buyer_name]
            found_message = f"FOUND {rq} {item_name} {price}"
            udp_socket.sendto(found_message.encode(), (buyer_client.ip, int(buyer_client.udp_port)))
            print(f"Sent FOUND to {buyer_name} for item {item_name} at price {price}")
            # Store the reservation
            reservations[rq] = {
                "seller_name": seller_name,
                "item_name": item_name,
                "price": max_price,
            }
            # Update the active search status instead of deleting
            active_searches[rq]["status"] = "RESERVED"
            active_searches[rq]["reserved_seller"] = seller_name
            active_searches[rq]["reserved_price"] = price

        else:
            # If no valid offers, attempt negotiation
            above_max_offers = [offer for offer in offers if offer[2] > max_price]
            if above_max_offers:
                lowest_above_max_offer = min(above_max_offers, key=lambda x: x[2])
                seller_name, item_name, lowest_price = lowest_above_max_offer

                seller_client = all_clients[seller_name]
                negotiate_message = f"NEGOTIATE {rq} {item_name} {max_price}"
                udp_socket.sendto(negotiate_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
                print(f"Sent NEGOTIATE to {seller_name} for item {item_name} at max price {max_price}")

            else:
                print(f"No valid offers found for {rq}. Cleaning up.")
                del active_searches[rq]  # Clean up only when no negotiation is possible

    def process_offer(rq, offer_name, item_name, price):
        """Process an OFFER message from a client."""
        global udp_socket
        if rq in active_searches:
            search_info = active_searches[rq]
            search_info["offers"].append((offer_name, item_name, int(price)))
            print(f"Received OFFER from {offer_name} for {item_name} at price {price}")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during OFFER processing.")

    def process_accept(rq, seller_name, item_name, max_price):
        """Process an ACCEPT message from a seller."""
        global reservations
        if rq in active_searches:
            search_info = active_searches[rq]
            buyer_name = search_info["requester_name"]

            if buyer_name in all_clients:
                buyer_client = all_clients[buyer_name]

                # Send FOUND message to the buyer to confirm availability
                found_message = f"FOUND {rq} {item_name} {max_price}"
                udp_socket.sendto(found_message.encode(), (buyer_client.ip, int(buyer_client.udp_port)))
                print(f"Sent FOUND to {buyer_name} for item {item_name} at price {max_price}")

                # Store the reservation
                reservations[rq] = {
                    "seller_name": seller_name,
                    "item_name": item_name,
                    "price": max_price,
                }
                print(f"Reservation created for {rq}: {reservations[rq]}")

                # Log reservation creation
                log_action(f"Reservation created: {reservations[rq]}")

                del active_searches[rq]
            else:
                print(f"ERROR: Buyer {buyer_name} not found in all_clients.")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during ACCEPT.")

    def process_refuse(rq, seller_name, item_name, max_price):
        """Process a REFUSE message from a seller."""
        global udp_socket
        if rq in active_searches:
            search_info = active_searches[rq]
            buyer_name = search_info["requester_name"]

            if buyer_name in all_clients:
                buyer_client = all_clients[buyer_name]

                # Send NOT_FOUND message to the buyer
                not_found_message = f"NOT_FOUND {rq} {item_name} {max_price}"
                udp_socket.sendto(not_found_message.encode(), (buyer_client.ip, int(buyer_client.udp_port)))
                print(f"Sent NOT_FOUND to {buyer_name} for item {item_name} at max price {max_price}")

                del active_searches[rq]
            else:
                print(f"ERROR: Buyer {buyer_name} not found in all_clients.")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during REFUSE.")

    def process_cancel(rq, buyer_name):
        """Process a CANCEL message from a buyer."""
        global udp_socket
        if rq in active_searches:
            # If the request exists in active_searches, proceed with cancellation
            search_info = active_searches[rq]
            seller_name = search_info.get("reserved_seller")

            if seller_name:
                # Send CANCEL message to the seller
                cancel_message = f"CANCEL {rq} {search_info['item_name']} {search_info.get('reserved_price', 'N/A')}"
                seller_client = all_clients[seller_name]
                udp_socket.sendto(cancel_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
                print(f"Sent CANCEL to {seller_name} for item {search_info['item_name']}")

            # Remove the reservation from active_searches
            del active_searches[rq]
            print(f"Request {rq} has been canceled and removed from active_searches.")
        else:
            # If the request doesn't exist in active_searches, log a message but don't raise an error
            print(f"Request {rq} not found in active_searches. It might have already been processed or canceled.")

    def process_buy(rq, buyer_name):
        """Process a BUY message and handle the transaction."""
        global reservations

        # Log the reservation state before lookup
        log_action(f"Current reservations: {reservations}")
        print(f"Looking up reservation for RQ: {rq}")

        if rq not in reservations:
            log_action(f"Reservation {rq} not found.")
            print(f"Reservation {rq} not found.")
            return

        transaction_info = reservations[rq]
        log_action(f"Reservation found: {transaction_info}")

        seller_name = transaction_info["seller_name"]
        item_name = transaction_info["item_name"]
        price = transaction_info["price"]

        # Ensure both buyer and seller exist
        if buyer_name not in all_clients or seller_name not in all_clients:
            print("Buyer or seller not registered.")
            return

        buyer = all_clients[buyer_name]
        seller = all_clients[seller_name]

        # Prepare TCP connections
        buyer_conn = (buyer.ip, int(buyer.tcp_port))
        seller_conn = (seller.ip, int(seller.tcp_port))
        inform_message = f"INFORM_Req {rq} {item_name} {price}"

        try:
            # Send INFORM_Req to buyer and seller
            print(f"Sending INFORM_Req to buyer ({buyer.name}) and seller ({seller.name})")
            buyer_response = send_and_receive_tcp(buyer_conn, inform_message)
            seller_response = send_and_receive_tcp(seller_conn, inform_message)

            # If both responses are received, simulate transaction
            if buyer_response and seller_response:
                print(f"Transaction successful for {item_name} at price {price}")
                log_action(f"Transaction completed for {item_name} at {price}.")
                del reservations[rq]
            else:
                # Handle transaction failure
                print(f"Transaction failed for {item_name}. Sending CANCEL messages.")
                cancel_message = f"CANCEL {rq} Transaction failed"
                send_tcp_message(buyer_conn, cancel_message)
                send_tcp_message(seller_conn, cancel_message)

        except Exception as e:
            print(f"Error during transaction: {e}")
            cancel_message = f"CANCEL {rq} Transaction error"
            send_tcp_message(buyer_conn, cancel_message)
            send_tcp_message(seller_conn, cancel_message)


        except Exception as e:
            print(f"Error during transaction: {e}")
            cancel_message = f"CANCEL {rq} Transaction error"
            send_tcp_message(buyer_conn, cancel_message)
            send_tcp_message(seller_conn, cancel_message)

    def send_and_receive_tcp(connection, message):
        """Send a message over TCP and wait for a response."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                tcp_socket.settimeout(300)  # Set a timeout
                tcp_socket.connect(connection)
                tcp_socket.sendall(message.encode())
                print(f"Sent message: {message}")

                response = tcp_socket.recv(1024).decode()  # Receive response
                print(f"Received response: {response}")
                return response  # Return the response
        except socket.timeout:
            print(f"Error: TCP connection to {connection} timed out.")
        except ConnectionRefusedError:
            print(f"Error: Connection to {connection} was refused.")
        except Exception as e:
            print(f"Error in TCP communication: {e}")
        return None  # Return None in case of an error

    def send_tcp_message(connection, message):
        """Send a message over TCP without waiting for a response."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                tcp_socket.settimeout(5)  # Set a timeout of 5 seconds
                tcp_socket.connect(connection)
                tcp_socket.sendall(message.encode())
                print(f"Sent message: {message}")
        except socket.timeout:
            print(f"Error: TCP connection to {connection} timed out.")
        except ConnectionRefusedError:
            print(f"Error: Connection to {connection} was refused.")
        except Exception as e:
            print(f"Error sending TCP message: {e}")

    def handle_message(message, client_address, type):
        global udp_socket
        parts = message.split()
        command = parts[0]
        rq = parts[1]

        if command == "REGISTER":
                name, ip, udp_port, tcp_port = parts[2:]
                if name in all_clients:
                    response = f"REGISTER-DENIED {rq} Name already registered"
                else:
                    all_clients[name] = Client(name, ip, udp_port, tcp_port)
                    response = f"REGISTERED {rq}"
                    log_action(f"Client {name} registered with IP {ip}, UDP Port {udp_port}, TCP Port {tcp_port}")
                    save_data()
                udp_socket.sendto(response.encode(), client_address)

        elif command == "DE-REGISTER":
            name = parts[2]
            if name in all_clients:
                del all_clients[name]
                response = f"DE-REGISTERED {rq}"
                log_action(f"Client {name} de-registered")
                save_data()
            else:
                response = f"DE-REGISTER-FAILED {rq} Not registered"
            udp_socket.sendto(response.encode(), client_address)

        elif command == "LOOKING_FOR":
            requester_name = parts[2]
            item_name = parts[3]
            description = parts[4]
            max_price = parts[5]

            print(f"{requester_name} is looking for {item_name} (Description: {description}, Max Price: {max_price})")
            log_action(f"{requester_name} is looking for {item_name} (Description: {description}, Max Price: {max_price})")
            broadcast_search(rq, requester_name, item_name, description, max_price)
            response = f"LOOKING_FOR_ACK {rq} SEARCH request broadcasted"
            udp_socket.sendto(response.encode(), client_address)

        elif command == "OFFER":
            offer_name = parts[2]
            item_name = parts[3]
            price = parts[4]
            print(f"Received OFFER from {offer_name} for {item_name} at price {price}")
            log_action(f"Received OFFER from {offer_name} for {item_name} at price {price}")
            process_offer(rq, offer_name, item_name, price)

        elif command == "ACCEPT":
            seller_name = parts[2]
            item_name = parts[3]
            max_price = parts[4]
            print(f"Received ACCEPT from {seller_name} for item {item_name} at max price {max_price}")
            log_action(f"Received ACCEPT from {seller_name} for item {item_name} at max price {max_price}")
            process_accept(rq, seller_name, item_name, max_price)

        elif command == "REFUSE":
            seller_name = parts[2]
            item_name = parts[3]
            max_price = parts[4]
            print(f"Received REFUSE from {seller_name} for item {item_name} at max price {max_price}")
            log_action(f"Received REFUSE from {seller_name} for item {item_name} at max price {max_price}")
            process_refuse(rq, seller_name, item_name, max_price)

        elif command == "CANCEL":
            buyer_name = parts[2]
            print(f"Received CANCEL from {buyer_name} for request {rq}")
            log_action(f"Received REFUSE from {buyer_name}")
            process_cancel(rq, buyer_name)

        elif command == "BUY":
            buyer_name = parts[2]
            print(f"Received BUY from {buyer_name} for request {rq}")
            log_action(f"Received REFUSE from {buyer_name}")
            process_buy(rq, buyer_name)


    def TCP_listener(port):
        global tcp_socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.bind((server_ip, port))
            tcp_socket.listen(10)
            print(f"TCP socket started {server_ip}:{port}")

            while True:
                conn, client_address = tcp_socket.accept()
                with conn:
                    message = conn.recv(buffer_size)
                    print(f"Received TCP message from {client_address}: {message.decode()}")
                    threading.Thread(target=handle_message, args=(message.decode(), client_address, 'TCP'), daemon=True).start()
                    load_data()
    def UDP_listener(port):
        global udp_socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.bind((server_ip, port))
            print(f"UDP socket started {server_ip}:{port}")

            while True:
                message, client_address = udp_socket.recvfrom(buffer_size)
                print(f"Received UDP message from {client_address}: {message.decode()}")

                threading.Thread(target=handle_message, args=(message.decode(), client_address, 'UDP'), daemon=True).start()
    load_data()
    print(f"Starting server with ip: {server_ip} TCP port: {tcp_port} UDP port: {udp_port} ")

    threading.Thread(target=TCP_listener, args=(tcp_port,), daemon=True).start()
    threading.Thread(target=UDP_listener, args=(udp_port,), daemon=True).start()

    while True:
        pass  # Prevent the main program from exiting


if __name__ == "__main__":
    start_server()
