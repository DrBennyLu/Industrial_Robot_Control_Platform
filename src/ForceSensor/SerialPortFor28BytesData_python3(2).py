#!/usr/bin/env python
# -*- coding:utf-8 -*-
import binascii
import struct
import serial
import time

try:
    portx = "COM8"  #in Windows it maybe COM15 or  COM3 // in linux it maybe /dev/ttyUSB0 or /dev/ttyUSB1
    bps = 460800
    ser = serial.Serial(portx, bps)
    if ser.isOpen():
        print("open success")
    readed_data = bytearray()
    data_to_deal = bytearray()
    wrench = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    now = time.strftime("%Y%m%d%H%M%S", time.localtime(time.time()))
    fname = now + r"tran.txt"
    f = open(fname, "w")
    serialsendcommand = [0x48, 0xAA, 0x0D, 0x0A]  # 此处2.7和3版本写法不同
    serialsendcommandhex = serialsendcommand
    # serialsendcommandHex = binascii.b2a_hex(serialsendcommand)
    # serialsendcommandhex = serialsendcommandHex.decode("hex")
    ser.write(serialsendcommandhex)
    while True:
        # send command
        # ser.write(serialsendcommandhex)
        # read and push to buffer
        count = ser.inWaiting()
        if count > 0:
            data = ser.read(count)
            datalist = bytearray(data)
            for i in range(count):
                readed_data.append(datalist[i])
        # deal the buffer
        while len(readed_data) > 27:
            readed_data_len = len(readed_data)
            if (readed_data_len >= 28) and (readed_data[26] == 0x0d) and (readed_data[27] == 0x0a):
                # for i in range(0,28):
                # data_to_deal.append(readed_data.pop(0)) #////////////////
                data_to_deal = bytearray()
                for i in range(0, 4):
                    data_to_deal.append(readed_data[5 - i])
                wrench[0] = struct.unpack("!f", data_to_deal)[0]
                data_to_deal = bytearray()
                for i in range(0, 4):
                    data_to_deal.append(readed_data[9 - i])
                wrench[1] = struct.unpack("!f", data_to_deal)[0]
                data_to_deal = bytearray()
                for i in range(0, 4):
                    data_to_deal.append(readed_data[13 - i])
                wrench[2] = struct.unpack("!f", data_to_deal)[0]
                data_to_deal = bytearray()
                for i in range(0, 4):
                    data_to_deal.append(readed_data[17 - i])
                wrench[3] = struct.unpack("!f", data_to_deal)[0]
                data_to_deal = bytearray()
                for i in range(0, 4):
                    data_to_deal.append(readed_data[21 - i])
                wrench[4] = struct.unpack("!f", data_to_deal)[0]
                data_to_deal = bytearray()
                for i in range(0, 4):
                    data_to_deal.append(readed_data[25 - i])
                wrench[5] = struct.unpack("!f", data_to_deal)[0]
                for i in range(0, 28):
                    readed_data.pop(0)
                print(wrench)  # This is the F/T Data
                f.write(''.join(str(i) for i in wrench) + "\n")
            elif readed_data_len >= 28:
                if readed_data[0] == 0x0a:
                    readed_data.pop(0)
                else:
                    i = 0
                    while (i <= 28) and (readed_data[0] != 0x0d) and (readed_data[1] != 0x0a):
                        readed_data.pop(0)
                        i = i + 1
                    readed_data.pop(0)
                    readed_data.pop(0)
            # elif(readed_data_len>=81):
            # for i in range(readed_data_len):
            # readed_data.pop(0)
        # time.sleep(0.005)
except Exception as e:
    print("Error：", e)
