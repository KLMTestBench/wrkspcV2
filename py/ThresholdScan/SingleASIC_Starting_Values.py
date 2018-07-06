#!/usr/bin/env python
import sys
import time
import os
import csv
import powerlaw
from array import array
sys.path.append('/home/testbench2/root_6_08/lib')
from ROOT import TCanvas, TGraph
from ROOT import gROOT, TF1
SCRIPTPATH = os.getcwd()#os.path.dirname(__file__)
sys.path.append( SCRIPTPATH+'/lib/' )
import linkEth
t1=time.time()

################################################################################
##         ----- Roughly Set Thresholds & Gains for One ASIC -----
##      This script first sets the threshold base value for every channel on one
##  ASIC, i.e. it sets the vertical position knob of this 160 channel oscilloscope
##  to zero. Next, it sets the trigger threshold to 150 DAC counts and
##  repeatedily counts the number of trigger scalers within a period defined by
##  the firmware while sweeping the HV over all 256 possible values (a 5 volt,
##  8 bit DAC that trims voltage from the raw inupt voltage). The trigger
##  scalers are printed to the terminal and meanwhile the program looks for
##  scaler frequencies closest to flow and fhigh defined below. Note, these
##  parameters will vary from one type of MPPC to another.
##      All of the values are written to file using a format that subsequent
##  data collection scritps can read and recognize.
##
##  Author: Chris Ketter
##
##  Last Modified: 10 Jan 2018
##
################################################################################

#---------------- USAGE ----------------#
usageMSG="\nUsage:\n"+\
"\tsudo ./SingleASIC_Starting_Values.py <S/N> <HV> <ASIC>\n\n"+\
"Where:\n"+\
    "\t<S/N>       = KLMS_0XXX\n"+\
    "\t<HV>        = (e.g.) 74p9\n"+\
    "\t<ASIC>      = (e.g.) 0\n"+\
    "\t<chNomask>  = (e.g.) 0100000000000001\n"

if len(sys.argv)==5:
    SN          = str(sys.argv[1])
    rawHV       = str(sys.argv[2])
    asicNo      = int(sys.argv[3])
    chNomask    = str(sys.argv[4])
if len(sys.argv)!=5:
    print usageMSG
    exit(-1)

fHigh = 750
fLow = 175
thOffset = 25

#--------- ETHERNET CONFIGURATION ----------#
addr_fpga = '192.168.20.5'
addr_pc = '192.168.20.1'
port_pc = '28672'
port_fpga = '24576'
syncwd="000000010253594e4300000000" # must be send before every command string
# Make UDP class for receiving/sending UDP Packets
ctrl = linkEth.UDP(addr_fpga, port_fpga, addr_pc, port_pc, "eth4")
ctrl.open()

#--- BUILD COMMANDS TO SET TRIG. THRESHOLD AND HV TO NULL ---#
cmdZeroTh = cmdHVoff = syncwd
for Ich in range (0,16):
    cmdHVoff  += hex( int('C',16)*(2**28) | asicNo*(2**20) | (Ich)*(2**16) | 255 ).split('x')[1]#+"AE000100"
    cmdZeroTh += hex( int('B',16)*(2**28) | asicNo*(2**24) | (2*Ich)*(2**16) | 0 ).split('x')[1]#+"AE000100"
ctrl.send(cmdHVoff)
time.sleep(0.1)
ctrl.send(cmdZeroTh)
time.sleep(0.1)

# --- CONFIGURE SCROD REGISTERS FOR COUNTING TRIGGER SCALERS --- #
ctrl.send(syncwd+'AF4D0B00'+'AE000100'+'AF4DCB00') # for KLM SciFi -- don't know why it's here
time.sleep(0.1)
ctrl.send(syncwd+'AF2F0004'+'AF300004')# 0000 0000 0000 0100 --> (47) TRIG_SCALER_CLK_MAX, (48) TRIG_SCALER_CLK_MAX_TRIGDEC
time.sleep(0.1)
ctrl.send(syncwd+'AF4A0136')# 0011 0110 (7 downto 0) WAVE_TRIGASIC_DUMP_CFG, 0001 (11 downto 8) PEDSUB_DATAOUT_MODE
time.sleep(0.1)


#--------------------------------------------------------------------------#
#----------------------SET GAIN AND TRIGGER THRESHOLDS---------------------#
#--------------------------------------------------------------------------#
T0 = 1000*4*2**16/63.5e6 # Clock period in ms (used for counting scalerCount)

thBase   = [3200 for i in range(15) ]
hvLow    = [255  for i in range(15) ]
hvHigh   = [255  for i in range(15) ]
TrigFreq = [0    for i in range(256)]

for chNo in range(15):
    if ((2**chNo & int(chNomask,2)) > 0):
        #---------- THRESHOLD SCAN (HV OFF) ----------#
        fmax = -1
        freq = 0
        ctrl.send(cmdHVoff)
        time.sleep(0.1)
        ctrl.send(cmdZeroTh)#set all trigs to 0
        time.sleep(0.1)
        print "\n*********** -Ch%d- ***********" % chNo
        print "Counting scalar frequencies at different thresholds (HV off)."
        for th in range (3700,3400,-1):
            cmdTh = syncwd + hex( int('B',16)*(2**28) | asicNo*(2**24) | (2*chNo)*(2**16) | th ).split('x')[1]#+"AE000100"
            ctrl.send(cmdTh)
            time.sleep(0.01)#wait for counters to settle then read registers
            # (scalerCount is 32-bit value shared between 2 16-bit registers)
            scalerCount = ctrl.readReg(138+asicNo) + ctrl.readReg(168+asicNo)*65536
            #print "test"
            if scalerCount > 0:
                sys.stdout.write("\nTrigDac=%3d " % th)
            #--- PICK OUT MAX SCALAR FREQ. AND ASSOC. THRESHOLD VALUE ---#
            freq = (scalerCount)/T0
            if scalerCount > 0:
                sys.stdout.write("%6.0f " % freq)# "Threshold: %8d\tScaler Count: %d" % (th, scalerCount)
            if (freq > fmax):
                fmax = freq
                thBase[chNo] = th

        print "\n\nMax Scalar Freq:"
        sys.stdout.write("%.1f " % fmax)

        print "\n\nThreshold Base:"
        sys.stdout.write("%d " % thBase[chNo])
        time.sleep(1.0)
        #---------- TRIM-DAC SCAN ----------#
        cmdTh = syncwd
        cmdTh += hex( int('B',16)*(2**28) | asicNo*(2**24) | (2*chNo)*(2**16) | thBase[chNo]-thOffset ).split('x')[1]#+"AE000100"
        ctrl.send(cmdTh)
        time.sleep(0.01)

        minDeltaF = 20000.
        print "\nPerforming HV scan for channel %d" % chNo
        x = array('d')
        y = array('d')
        fdiffHigh = 100000
        fdiffLow  = 100000
        for hv in range (255,-1,-1): # 255 is lowest HV setting (i.e. most trim)
            cmdHV = syncwd
            cmdHV += hex( int('C',16)*(2**28) | asicNo*(2**20) | (chNo)*(2**16) | hv ).split('x')[1]#+"AE000100"
            ctrl.send(cmdHV)
            time.sleep(0.01)#wait for counters to settle then read registers
            scalerCount = ctrl.readReg(138+asicNo) + ctrl.readReg(168+asicNo)*65536
            if scalerCount > 0:
                sys.stdout.write("\nhvTrim=%3d " % hv)
            TrigFreq[hv] = scalerCount/T0
            if scalerCount > 0:
                sys.stdout.write("%6.0f " % TrigFreq[hv])
            if scalerCount>0:
                x.append(hv)
                y.append(TrigFreq[hv])
            if abs(TrigFreq[hv]-fHigh) < fdiffHigh:
                fdiffHigh = abs(TrigFreq[hv]-fHigh)
                hvHigh[chNo] = hv
            if abs(TrigFreq[hv]-fLow) < fdiffLow:
                fdiffLow = abs(TrigFreq[hv]-fLow)
                hvLow[chNo] = hv
        ctrl.send(cmdHVoff)
        time.sleep(0.01)#wait for counters to settle then read registers
        print "\n\nFound starting HV values.\nhvLow:"
        sys.stdout.write("%d " % hvLow[chNo])
        print "\nhvHigh:"
        sys.stdout.write("%d " % hvHigh[chNo])
        maxValue = max(TrigFreq)
        if maxValue < fHigh:
            print "\nWARNING: ASIC %d ch. %d scalers too low, raw HV may be out of range" % (asicNo, chNo)
        if maxValue==0:
            print "WARNING: ASIC %d ch. %d scalers all zero." % (asicNo, chNo)
            print "likely causes:"
            print "     -->raw HV out of range"
            print "     -->loose/disconnected ribbon cable"


#----WRITE CALIBRATION DATA TO FILE ----#
if not (os.path.isdir("data/%s/calib/HVandTH" % SN)): # create path if it does not exist
    print "\nmaking directory data/%s/calib/HVandTH" % SN
    os.system("mkdir -p data/%s/calib/HVandTH" % SN) # make deepest subdir with parents
    os.system("sudo chown -R testbench2:testbench2 data/%s/calib/" % SN) # recursively change ownership

calib_file_name = "data/"+SN+"/calib/HVandTH/"+SN+"_HV"+rawHV+"_"+"ASIC"+str(asicNo)+".txt"
outfile = open(calib_file_name, 'w')
for i in range(15):
    outfile.write("%d\t%d\t%d\n" % (thBase[i], hvLow[i], hvHigh[i]))
outfile.close()

ctrl.close()

deltaTime = (time.time()-t1)/60
print "\nCalibration Completed in %.2f min." % deltaTime
print "\nResults:"
print "\nThreshold base:"
print(thBase)
print "\n\nHV low values:"
print(hvLow)
print "\n\nHV high values:"
print(hvHigh)
print "Writing calibration values in %s" % calib_file_name
