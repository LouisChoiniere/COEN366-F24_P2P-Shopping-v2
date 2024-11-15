import socket
import threading
import time

class Client:
    def __init__(self, name, ip, udp_port, tcp_port):
        self.name = name
        self.ip = ip
        self.udp_port = udp_port
        self.tcp_port = tcp_port

def start_server():
    server_ip = "0.0.0.0"
    server_port = 5000
    buffer_size = 1024
    all_clients = {}
    active_searches = {}
    reservations = {}

    def broadcast_search(rq, requester_name, item_name, description, max_price):
        """Send SEARCH message to all clients except the requester."""
        num_sellers = 0
        for client_key, client in all_clients.items():
            if client.name != requester_name:
                search_message = f"SEARCH {rq} {item_name} {description}"
                server_socket.sendto(search_message.encode(), (client.ip, int(client.udp_port)))
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

    def check_offers_after_timeout(rq):
        """Evaluate offers after waiting for 5 minutes or receiving all expected offers."""
        timeout = 300
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
            server_socket.sendto(reserve_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
            print(f"Sent RESERVE to {seller_name} for item {item_name} at price {price}")

            # Notify the buyer about the availability
            buyer_client = all_clients[buyer_name]
            found_message = f"FOUND {rq} {item_name} {price}"
            server_socket.sendto(found_message.encode(), (buyer_client.ip, int(buyer_client.udp_port)))
            print(f"Sent FOUND to {buyer_name} for item {item_name} at price {price}")

            # Store reservation information
            reservations[rq] = {"seller_name": seller_name, "item_name": item_name, "price": price}
        else:
            # If no valid offers, attempt negotiation
            above_max_offers = [offer for offer in offers if offer[2] > max_price]
            if above_max_offers:
                lowest_above_max_offer = min(above_max_offers, key=lambda x: x[2])
                seller_name, item_name, lowest_price = lowest_above_max_offer

                seller_client = all_clients[seller_name]
                negotiate_message = f"NEGOTIATE {rq} {item_name} {max_price}"
                server_socket.sendto(negotiate_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
                print(f"Sent NEGOTIATE to {seller_name} for item {item_name} at max price {max_price}")

    def process_offer(rq, offer_name, item_name, price):
        """Process an OFFER message from a client."""
        if rq in active_searches:
            search_info = active_searches[rq]
            search_info["offers"].append((offer_name, item_name, int(price)))
            print(f"Received OFFER from {offer_name} for {item_name} at price {price}")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during OFFER processing.")

    def process_accept(rq, seller_name, item_name, max_price):
        """Process an ACCEPT message from a seller."""
        if rq in active_searches:
            search_info = active_searches[rq]
            buyer_name = search_info["requester_name"]

            if buyer_name in all_clients:
                buyer_client = all_clients[buyer_name]

                # Send FOUND message to the buyer to confirm availability at max price
                found_message = f"FOUND {rq} {item_name} {max_price}"
                server_socket.sendto(found_message.encode(), (buyer_client.ip, int(buyer_client.udp_port)))
                print(f"Sent FOUND to {buyer_name} for item {item_name} at price {max_price}")

                del active_searches[rq]
            else:
                print(f"ERROR: Buyer {buyer_name} not found in all_clients.")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during ACCEPT.")

    def process_refuse(rq, seller_name, item_name, max_price):
        """Process a REFUSE message from a seller."""
        if rq in active_searches:
            search_info = active_searches[rq]
            buyer_name = search_info["requester_name"]

            if buyer_name in all_clients:
                buyer_client = all_clients[buyer_name]

                # Send NOT_FOUND message to the buyer
                not_found_message = f"NOT_FOUND {rq} {item_name} {max_price}"
                server_socket.sendto(not_found_message.encode(), (buyer_client.ip, int(buyer_client.udp_port)))
                print(f"Sent NOT_FOUND to {buyer_name} for item {item_name} at max price {max_price}")

                del active_searches[rq]
            else:
                print(f"ERROR: Buyer {buyer_name} not found in all_clients.")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during REFUSE.")

    def process_cancel(rq, buyer_name):
        """Process a CANCEL message from a buyer."""
        if rq in active_searches:
            search_info = active_searches[rq]
            seller_name = search_info.get("reserved_seller")

            if seller_name:
                # Send CANCEL message to the seller
                cancel_message = f"CANCEL {rq} {search_info['item_name']} {search_info['reserved_price']}"
                seller_client = all_clients[seller_name]
                server_socket.sendto(cancel_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
                print(f"Sent CANCEL to {seller_name} for item {search_info['item_name']}")

                # Remove the reservation
                del active_searches[rq]
            else:
                print(f"ERROR: No reservation found for request {rq} during CANCEL.")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during CANCEL.")

    def process_buy(rq, buyer_name):
        """Process a BUY message from a buyer."""
        if rq in active_searches:
            search_info = active_searches[rq]
            seller_name = search_info.get("reserved_seller")

            if seller_name:
                # Send BUY message to the seller
                buy_message = f"BUY {rq} {search_info['item_name']} {search_info['reserved_price']}"
                seller_client = all_clients[seller_name]
                server_socket.sendto(buy_message.encode(), (seller_client.ip, int(seller_client.udp_port)))
                print(f"Sent BUY to {seller_name} for item {search_info['item_name']}")

                # Remove the reservation as it is completed
                del active_searches[rq]
            else:
                print(f"ERROR: No reservation found for request {rq} during BUY.")
        else:
            print(f"ERROR: Request {rq} not found in active_searches during BUY.")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        server_socket.bind((server_ip, server_port))
        print(f"Server started at {server_ip}:{server_port}")

        while True:
            message, client_address = server_socket.recvfrom(buffer_size)
            print(f"Received message from {client_address}: {message.decode()}")
            message = message.decode()
            parts = message.split()

            command = parts[0]
            rq = parts[1]  # Extract the request number for responses

            if command == "REGISTER":
                name, ip, udp_port, tcp_port = parts[2:]
                if name in all_clients:
                    response = f"REGISTER-DENIED {rq} Name already registered"
                else:
                    all_clients[name] = Client(name, ip, udp_port, tcp_port)
                    response = f"REGISTERED {rq}"
                server_socket.sendto(response.encode(), client_address)

            elif command == "DE-REGISTER":
                name = parts[2]
                if name in all_clients:
                    del all_clients[name]
                    response = f"DE-REGISTERED {rq}"
                else:
                    response = f"DE-REGISTER-FAILED {rq} Not registered"
                server_socket.sendto(response.encode(), client_address)

            elif command == "LOOKING_FOR":
                requester_name = parts[2]
                item_name = parts[3]
                description = parts[4]
                max_price = parts[5]

                print(f"{requester_name} is looking for {item_name} (Description: {description}, Max Price: {max_price})")

                broadcast_search(rq, requester_name, item_name, description, max_price)
                response = f"LOOKING_FOR_ACK {rq} SEARCH request broadcasted"
                server_socket.sendto(response.encode(), client_address)

            elif command == "OFFER":
                offer_name = parts[2]
                item_name = parts[3]
                price = parts[4]
                print(f"Received OFFER from {offer_name} for {item_name} at price {price}")

                process_offer(rq, offer_name, item_name, price)

            elif command == "ACCEPT":
                seller_name = parts[2]
                item_name = parts[3]
                max_price = parts[4]
                print(f"Received ACCEPT from {seller_name} for item {item_name} at max price {max_price}")

                process_accept(rq, seller_name, item_name, max_price)

            elif command == "REFUSE":
                seller_name = parts[2]
                item_name = parts[3]
                max_price = parts[4]
                print(f"Received REFUSE from {seller_name} for item {item_name} at max price {max_price}")

                process_refuse(rq, seller_name, item_name, max_price)

            elif command == "CANCEL":
                buyer_name = parts[2]
                print(f"Received CANCEL from {buyer_name} for request {rq}")

                process_cancel(rq, buyer_name)

            elif command == "BUY":
                buyer_name = parts[2]
                print(f"Received BUY from {buyer_name} for request {rq}")

                process_buy(rq, buyer_name)

if __name__ == "__main__":
    start_server()
