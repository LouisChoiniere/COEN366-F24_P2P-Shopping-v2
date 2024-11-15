# COEN366-F24_P2P-Shopping

## Introduction
Welcome to the Peer-to-Peer Shopping System (P2S2) project! This project is part of the Communication Networks and Protocols course (COEN 366) at Concordia University. The goal of this project is to create a shopping system where users can buy and sell items through a server that facilitates communication between peers.

## Project Overview
The Peer-to-Peer Shopping System (P2S2) allows users to search for items and purchase them from other users. The system consists of several peers (users) and one server. Users can register with the server, search for items, and finalize purchases. The server acts as an intermediary, ensuring that users do not communicate directly with each other.

## Features
- **User Registration and De-registration**: Users must register with the server to use the service. They can also de-register when they no longer wish to use the service.
- **Item Search**: Registered users can search for items they wish to buy. The server broadcasts the search request to all other registered users.
- **Offers and Negotiation**: Users who have the requested item can make offers. The server facilitates negotiation if the offer price is higher than the buyer's maximum price.
- **Purchase Finalization**: Once an agreement is reached, the server helps finalize the purchase by collecting payment information and providing shipping details.

## Communication
- **UDP Communication**: Used for registration, de-registration, and item search.
- **TCP Communication**: Used for finalizing purchases, including payment and shipping information.
