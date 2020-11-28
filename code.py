import datetime
import threading
import select
from socket import *
import time
import json
import random
import copy

NODES_COUNT = 6
NEIGHBOR_COUNT = 3
RUN_TIME = 300
TIME_TO_REMOVE_A_NEIGHBOR = 8
TIME_TO_SEND_A_MESSAGE = 2
SLEEP_DURATION = 20
SLEEP_INTERVAL = 10
DROPPING_PACKET_CHANCE = 5

nodes = []
sockets = []
ports = []
hosts = []
isOff = []
lastTimeNodeWentOff = 0
start = time.time()

class Host:
    def __init__(self, IP, port):
        self.IP = IP
        self.port = port

class NeighborsInformation:
    def __init__(self, host):
        self.host = host
        self.lastHelloRcvd = 0
        self.packetRecvCount = 0
        self.packetSentCount = 0
        self.timeBecameBi = 0
        self.reachableDuration = 0
        self.bidirNeighbors = []

    def updateTime(self):
        self.lastHelloRcvd = time.time()

    def updateAvailableTime(self):
        if self.timeBecameBi == 0:
            print("ERROR")
            return
        self.reachableDuration += (time.time() - self.timeBecameBi)
        self.timeBecameBi = 0

class UdpSocket:
    def __init__(self):
        self.socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        sockets.append(self.socket)

    def bindTo(self, port):
        try:
            self.socket.bind(("", int(port)))
        except:
            print("bind failed  ")
            return False
        return True

    def sendTo(self, message, dest):
        self.socket.sendto(message.encode(), (dest.IP, int(dest.port)))

    def recvFrom(self):
        self.socket.setblocking(0)
        received = self.socket.recvfrom(2048)[0].decode()
        return received

class HelloMessage:
    def __init__(self, sender, IP, port, bidirNeighbors, lastPacketRcvd):
        self.sender = sender
        self.IP = IP
        self.port = port
        self.bidirNeighbors = []
        for i in bidirNeighbors:
            self.bidirNeighbors.append(i.host.port)
        self.lastPacketRcvd = lastPacketRcvd
    def toJson(self):
        message = "{ \"IP\":" + "\"" + self.IP + "\"" + ', "port":' + "\"" + self.port + "\"" + ', "type":"HELLO_MSG"' + ', "bidirNeighbors":' +  "\"" + str(self.bidirNeighbors) +  "\"" + ', "lastPacketRcvd":' + "\"" + str(self.lastPacketRcvd) + "\"" + ', "lastPacketSenderSentToreceiver":' + "\"" + str(time.time()) + "\"" "}"
        return message

class Node:
    def __init__(self, host, index):
        self.index = index
        self.host = host
        self.requested = []
        self.allNeighbors = []
        self.bidirNeighbors = []
        self.udpSocket = UdpSocket()
        self.udpSocket.bindTo(host.port)
        self.sendTime = 0
        thread = threading.Thread(target=self.handler, args=())
        thread.start()
    
    def handler(self):
        global start 
        self.sendTime = time.time()
        while(True):
            if time.time() - start > RUN_TIME:
                for neighbor in self.bidirNeighbors:
                    self.findInList(self.allNeighbors, neighbor.host.port).updateAvailableTime()
                break

            if isOff[self.index] != 0:
                continue

            
            self.receive()

            for neighbor in self.bidirNeighbors:
                if time.time() - neighbor.lastHelloRcvd >= TIME_TO_REMOVE_A_NEIGHBOR:
                    self.bidirNeighbors.remove(neighbor)
                    self.findInList(self.allNeighbors, neighbor.host.port).updateAvailableTime()

            for neighbor in self.requested:
                if time.time() - neighbor.lastHelloRcvd >= TIME_TO_REMOVE_A_NEIGHBOR:
                    self.requested.remove(neighbor)

            if time.time() - self.sendTime >= TIME_TO_SEND_A_MESSAGE:
                self.send()

    def send(self):
        self.sendTime = time.time()
        for node in self.bidirNeighbors:
            message = HelloMessage(self.index, self.host.IP, self.host.port, self.bidirNeighbors, node.lastHelloRcvd)
            self.udpSocket.sendTo(message.toJson(), node.host)
            self.findInList(self.allNeighbors, node.host.port).packetSentCount += 1

    
        if len(self.bidirNeighbors) == NEIGHBOR_COUNT:
            return

        rand = random.randint(0, NODES_COUNT-1)
        if not (self.index == rand or self.isInList(self.bidirNeighbors, hosts[rand].port)):
            if self.isInList(self.requested, hosts[rand].port):
                self.findInList(self.requested, hosts[rand].port).updateTime()
            else:
                tempNeighbor = NeighborsInformation(hosts[rand])
                tempNeighbor.updateTime()
                self.requested.append(tempNeighbor)
        
        for node in self.requested:
            message = HelloMessage(self.index, self.host.IP, self.host.port, self.bidirNeighbors, node.lastHelloRcvd)
            self.udpSocket.sendTo(message.toJson(), node.host)
        
    def receive(self):
        try:
            rand = random.randint(1, 100)
            if rand <= DROPPING_PACKET_CHANCE:
                return
            
            received = self.udpSocket.recvFrom()
            received = json.loads(received)
            senderPort = received["port"]
            senderBidirNeighbors = received["bidirNeighbors"]

            if self.isInList(self.bidirNeighbors, senderPort):
                self.findInList(self.bidirNeighbors, senderPort).updateTime()
                self.findInList(self.allNeighbors, senderPort).packetRecvCount += 1
                self.findInList(self.bidirNeighbors, senderPort).bidirNeighbors = received["bidirNeighbors"]
                return

            if self.isInList(self.requested, senderPort):
                self.findInList(self.requested, senderPort).bidirNeighbors = received["bidirNeighbors"]

            if len(self.bidirNeighbors) == NEIGHBOR_COUNT:
                return

            if self.isInList(self.requested, senderPort):
                self.requested, self.bidirNeighbors = self.moveFromTo(self.requested, self.bidirNeighbors, senderPort)
                self.findInList(self.bidirNeighbors, senderPort).updateTime()
                self.findInList(self.bidirNeighbors, senderPort).bidirNeighbors = received["bidirNeighbors"]
                if not self.isInList(self.allNeighbors, senderPort):
                    neighbor = NeighborsInformation(Host(received["IP"], senderPort))
                    if self.isInBidirList(senderBidirNeighbors):
                        neighbor.packetRecvCount = 1
                    neighbor.timeBecameBi = time.time()
                    self.allNeighbors.append(neighbor)
                else:
                    neighbor = self.findInList(self.allNeighbors, senderPort)
                    neighbor.timeBecameBi = time.time()
            else:
                newNeighbor = NeighborsInformation(Host(received["IP"], senderPort))
                newNeighbor.updateTime()
                newNeighbor.bidirNeighbors = received["bidirNeighbors"]
                self.requested.append(newNeighbor)
        
        except BlockingIOError:
            pass

    def findInList(self, list, port):
        for i in range (0, len(list)):
            if list[i].host.port == port:
                return list[i]

    def isInList(self, list, port):
        for i in list:
            if port == i.host.port:
                return True
        return False

    def isInBidirList(self, li):
        res = li.strip('][').split(', ')
        for port in res:
            if ("'" + self.host.port  + "'") == port:
                return True
        return False

    def moveFromTo(self, list1, list2, port):
        for i in list1:
            if i.host.port == port:
                list2.append(i)
                list1.remove(i)
                break
        return list1, list2

def writeJsonFile():
        data = []
        for node in nodes:
            data_ = []
            for i in node.allNeighbors:
                data_.append("IP: " + str(i.host.IP) + ", port: " +  str(i.host.port) + ", packetRecvCount: " + str(i.packetRecvCount) + ", packetSentCount: " + str(i.packetSentCount))
            data.append(data_)

        data2 = []
        for node in nodes:
            data_ = []
            for i in node.bidirNeighbors:
                print(i)
                data_.append(i.host.port)
            data2.append(data_)
             
        data3 = []
        for node in nodes:
            data_ = []
            for i in node.allNeighbors:
                data_.append(i.host.port + "    :   " +str(i.reachableDuration/RUN_TIME))
            data3.append(data_)

        data4 = []
        for node in nodes:
            data_ = []
            for i in node.requested:
                data_.append(i.host.port + " has these bidirNeighbors: " + str(i.bidirNeighbors))
            data4.append(data_)

        data5 = []
        for node in nodes:
            data_ = []
            for i in node.bidirNeighbors:
                print(i)
                data_.append(i.host.port + " has these bidirNeighbors: " + str(i.bidirNeighbors))
            data5.append(data_)

        counter = 0
        for node in nodes:
            fileName = str(node.index) + ".json"
            with open(fileName, 'w', encoding='utf-8') as f:
                print(data2[counter])
                json.dump("allTimeNeighbours:", f, ensure_ascii=False, indent=4)
                json.dump(data[counter], f, ensure_ascii=False, indent=4)
                json.dump("bidirNeighbors:", f, ensure_ascii=False, indent=4)
                json.dump(data2[counter], f, ensure_ascii=False, indent=4)
                json.dump("availability:", f, ensure_ascii=False, indent=4)
                json.dump(data3[counter], f, ensure_ascii=False, indent=4)
                json.dump("Topology:    bidir Neighbors:", f, ensure_ascii=False, indent=4)
                json.dump(data5[counter], f, ensure_ascii=False, indent=4)
                json.dump("Unidir Neighbors:", f, ensure_ascii=False, indent=4)
                json.dump(data4[counter], f, ensure_ascii=False, indent=4)
                counter += 1

def initialize():
    global lastTimeNodeWentOff
    for i in range(0,NODES_COUNT):
        ports.append(str(i + 8080))
        isOff.append(0)
        
    for port in ports:
        hosts.append(Host("", port))
        
    counter = 0
    for host in hosts:
        nodes.append(Node(host, counter))
        counter += 1

    while time.time() - start < RUN_TIME + 1:
        tempTime = time.time()
        for i in range(0,NODES_COUNT):
            if isOff[i] != 0 and tempTime - isOff[i] >= SLEEP_DURATION:
                isOff[i] = 0

        if tempTime - lastTimeNodeWentOff >= SLEEP_INTERVAL:
            randNode = random.randint(0, NODES_COUNT - 1)
            isOff[randNode] = tempTime
            lastTimeNodeWentOff = tempTime
        continue
    
initialize()
writeJsonFile()