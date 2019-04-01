#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Maintained by: AnalogMan
# Original Author: rkk (https://gbatemp.net/members/rkk.451877/)
# Thanks to: Zotan (https://github.com/zotanwolf), HE (Discord: HE#4681), Liam (Discord: Liam#7089)
# Modified Date: 2018-07-06
# Purpose: Prints info for game titles, downloads title files, repacks files into installable NSP. Uses Nintendo CDN.
# Requirements: requests, tqdm, pyopenssl

import os, sys
import subprocess
import requests
import urllib3
import json
import shutil
import argparse
import configparser
from hashlib import sha256
from struct import pack as pk, unpack as upk
from binascii import hexlify as hx, unhexlify as uhx
import xml.etree.ElementTree as ET, xml.dom.minidom as minidom
import re 

title_name = ''

def read_at(f, off, len):
    f.seek(off)
    return f.read(len)

def read_u8(f, off):
    return upk('<B', read_at(f, off, 1))[0]

def read_u16(f, off):
    return upk('<H', read_at(f, off, 2))[0]

def read_u32(f, off):
    return upk('<I', read_at(f, off, 4))[0]
    
def read_u48(f, off):
    return upk('<IH', read_at(f, off, 6))[0]

def read_u64(f, off):
    return upk('<Q', read_at(f, off, 8))[0]
    
def bytes2human(n, f='%(value).3f %(symbol)s'):
    n = int(n)
    if n < 0:
        raise ValueError("n < 0")
    symbols = ('B', 'KB', 'MB', 'GB', 'TB')
    prefix = {}
    for i, s in enumerate(symbols[1:]):
        prefix[s] = 1 << (i + 1) * 10
    for symbol in reversed(symbols[1:]):
        if n >= prefix[symbol]:
            value = float(n) / prefix[symbol]
            return f % locals()
    return f % dict(symbol=symbols[0], value=n)
    
def load_config(fPath):
    dir = os.path.dirname(__file__)
    config = {'Paths': {
                 'hactoolPath':  os.path.join(dir, 'hactool.exe'),
                 'keysPath':     os.path.join(dir, 'keys.txt'),
                 'NXclientPath': os.path.join(dir, 'nx_tls_dev_cert.pem'),
                 'ShopNPath':    os.path.join(dir, 'ShopN.pem')},
              'Values': {
                 'Region':      'US',
                 'Firmware':    '5.1.0-0',
                 'DeviceID':    '0000000000000000',
                 'Environment': 'lp1'}}
    try:
        f = open(fPath, 'r')
    except FileNotFoundError:
        print('Missing CDNSPconfig.json file!')
        raise
        
    j = json.load(f)
    
    for key1 in config:
        for key2 in j[key1]:
            config[key1].update({key2: j[key1][key2]})
            
    hactoolPath  = j['Paths']['hactoolPath']
    keysPath     = j['Paths']['keysPath']
    NXclientPath = j['Paths']['NXclientPath']
    ShopNPath    = j['Paths']['ShopNPath']
    
    reg          = j['Values']['Region']
    fw           = j['Values']['Firmware']
    did          = j['Values']['DeviceID']
    env          = j['Values']['Environment']
    
    return hactoolPath, keysPath, NXclientPath, ShopNPath, reg, fw, did, env

def make_request(method, url, certificate='', hdArgs={}):
    if certificate == '': # Workaround for defining errors
        certificate = NXclientPath

    reqHd = {'User-Agent': 'NintendoSDK Firmware/%s (platform:NX; did:%s; eid:%s)' % (fw, did, env),
             'Accept-Encoding': 'gzip, deflate',
             'Accept': '*/*',
             'Connection': 'keep-alive'}
    reqHd.update(hdArgs)
    
    r = requests.request(method, url, cert=certificate, headers=reqHd, verify=False, stream=True)
    
    if r.status_code == 403:
        print('Request rejected by server! Check your cert.')
        sys.exit()

    return r
    
def get_info(tid):
    global title_name
    print('\n%s:' % tid)
    
    if tid.endswith('000'):
        baseTid = tid
        updateTid = '%s800' % tid[:-3]
    elif tid.endswith('800'):
        baseTid = '%s000' % tid[:-3]
        updateTid = tid
    elif not tid.endswith('00'):
        baseTid = '%016x' % (int(tid, 16) - 0x1000 & 0xFFFFFFFFFFFFF000)
        updateTid = '%s800' % tid[:-3]
    else:
        print('\tInvalid shogun TitleID %s!' % tid)
        return
    
    t = ''

    for reg_list in list([reg, 'US', 'EU', 'AU', 'KR', 'TW', 'JP']):
        url = 'https://bugyo.hac.%s.eshop.nintendo.net/shogun/v1/contents/ids?shop_id=4&lang=en&country=%s&type=title&title_ids=%s'\
            % (env, reg_list, baseTid)
        r = make_request('GET', url, certificate=ShopNPath)
        if r.status_code == 200:
            t = r
        if r.status_code == 404:
            continue
        if len(r.json()['id_pairs']):
            break
            
    if r.status_code == 404:
        if t:
            r = t
        else:
            print('File not found on server: 404')
            sys.exit()

    j = r.json()
        
    try:
        nsuid = j['id_pairs'][0]['id']
        url = 'https://bugyo.hac.%s.eshop.nintendo.net/shogun/v1/titles/%s?shop_id=4&lang=en&country=%s' % (env, nsuid, reg_list)
        r = make_request('GET', url, certificate=ShopNPath)
        j = r.json()
        name = j['formal_name']

        title_name = re.sub(r'[/\\:*?"|™©®]+', "", name)
        
        try:
            size = j['total_rom_size']
        except KeyError:
            pass
        
        print('\tName: %s' % name)
        try:
            print('\tSize: %s' % bytes2human(size))
        except NameError:
            print('\t\tNo size was found for %s' % tid)
        print('\tBase TID:   %s' % baseTid)
        print('\tUpdate TID: %s' % updateTid)
    except IndexError:
        print('\tCan\'t get name of title, TitleID not found on Shogun!')
        title_name = 'Unknown'
    
    url = 'https://superfly.hac.%s.d4c.nintendo.net/v1/t/%s/dv' % (env,tid)
    r = make_request('GET', url)
    j = r.json()

    n = 0
    for game in j['titles']:
        n += 1
        if updateTid in game['id']:
            lastestVer = game['version']
            print('\tAvailable update versions for %s:' % updateTid)
            print('\t\tv%s' % " v".join(str(i) for i in range(0x10000, lastestVer+1, 0x10000)))
            break
    
    if n == len(j['titles']):
        print('\t%s has no update available!' % updateTid)

def download_file(url, fPath):
    fName = os.path.basename(fPath).split()[0]

    if os.path.exists(fPath):
        dlded = os.path.getsize(fPath)
        r = make_request('GET', url, hdArgs={'Range': 'bytes=%s-' % dlded})
        
        if r.headers.get('Server') != 'openresty/1.9.7.4':
            print('\t\tDownload is already complete, skipping!')
            return fPath
        elif r.headers.get('Content-Range') == None: # CDN doesn't return a range if request >= filesize
            fSize = int(r.headers.get('Content-Length'))
        else:
            fSize = dlded + int(r.headers.get('Content-Length'))
            
        if dlded == fSize:
            print('\t\tDownload is already complete, skipping!')
            return fPath
        elif dlded < fSize:
            print('\t\tResuming download...')
            f = open(fPath, 'ab')
        else:
            print('\t\tExisting file is bigger than expected (%s/%s), restarting download...' % (dlded, fSize))
            dlded = 0
            f = open(fPath, "wb")
    else:
        dlded = 0
        r = make_request('GET', url)
        fSize = int(r.headers.get('Content-Length'))
        f = open(fPath, 'wb')
        
    chunkSize = 1000
    if tqdmProgBar == True and fSize >= 10000:
        for chunk in tqdm(r.iter_content(chunk_size=chunkSize), initial=dlded//chunkSize, total=fSize//chunkSize,
                          desc=fName, unit='kb', smoothing=1, leave=False):
            f.write(chunk)
            dlded += len(chunk)
    elif fSize >= 10000:
        for chunk in r.iter_content(chunkSize): # https://stackoverflow.com/questions/15644964/python-progress-bar-and-downloads
            f.write(chunk)
            dlded += len(chunk)
            done = int(50 * dlded / fSize)
            sys.stdout.write('\r%s:  [%s%s] %d/%d b' % (fName, '=' * done, ' ' * (50-done), dlded, fSize) )    
            sys.stdout.flush()
        sys.stdout.write('\033[F')
    else:
        f.write(r.content)
        dlded += len(r.content)
    
    if fSize != 0 and dlded != fSize:
        raise ValueError('Downloaded data is not as big as expected (%s/%s)!' % (dlded, fSize))
        
    f.close()    
    print('\r\t\tSaved to %s!' % f.name)
    return fPath

def decrypt_NCA(fPath, outDir=''):
    fName = os.path.basename(fPath).split()[0]
    
    if outDir == '':
        outDir = os.path.splitext(fPath)[0]
    os.makedirs(outDir, exist_ok=True)
    
    commandLine = './' + hactoolPath + ' "' + fPath + '"' + keysArg\
                  + ' --exefsdir="'    + os.path.join(outDir, 'exefs') + '"'\
                  + ' --romfsdir="'    + os.path.join(outDir, 'romfs') + '"'\
                  + ' --section0dir="' + os.path.join(outDir, 'section0') + '"'\
                  + ' --section1dir="' + os.path.join(outDir, 'section1') + '"'\
                  + ' --section2dir="' + os.path.join(outDir, 'section2') + '"'\
                  + ' --section3dir="' + os.path.join(outDir, 'section3') + '"'\
                  + ' --header="'      + os.path.join(outDir, 'Header.bin') + '"'
                  
    try:            
        subprocess.check_output(commandLine, shell=True)
        if os.listdir(outDir) == []:
            raise subprocess.CalledProcessError('\nDecryption failed, output folder %s is empty!' % outDir)
    except subprocess.CalledProcessError:
        print('\nDecryption failed!')
        raise
        
    return outDir
    
def download_cetk(rightsID, fPath):
    url = 'https://atum.hac.%s.d4c.nintendo.net/r/t/%s?device_id=%s' % (env, rightsID, did)
    r = make_request('HEAD', url)
    id = r.headers.get('X-Nintendo-Content-ID')
    
    url = 'https://atum.hac.%s.d4c.nintendo.net/c/t/%s?device_id=%s' % (env, id, did)
    cetk = download_file(url, fPath)
    
    return cetk
        
def download_title(gameDir, tid, ver, tkey='', nspRepack=False, n=''):
    print('\n%s v%s:' % (tid, ver))
    if len(tid) != 16:
        tid = (16-len(tid)) * '0' + tid
        
    url = 'https://atum%s.hac.%s.d4c.nintendo.net/t/a/%s/%s?device_id=%s' % (n, env, tid, ver, did)
    r = make_request('HEAD', url)
    CNMTid = r.headers.get('X-Nintendo-Content-ID')
    if CNMTid == None:
        print('CNMT not found on server!')
        sys.exit()
    print('\tDownloading CNMT (%s.cnmt.nca)...' % CNMTid)
    url = 'https://atum%s.hac.%s.d4c.nintendo.net/c/a/%s?device_id=%s' % (n, env, CNMTid, did)
    fPath = os.path.join(gameDir, CNMTid + '.cnmt.nca')
    cnmtNCA = download_file(url, fPath)
    cnmtDir = decrypt_NCA(cnmtNCA)
    CNMT = cnmt(os.path.join(cnmtDir, 'section0', os.listdir(os.path.join(cnmtDir, 'section0'))[0]))
    
    if nspRepack == True:
        outf = os.path.join(gameDir, '%s.xml' % os.path.basename(cnmtNCA.strip('.nca')))
        cnmtXML = CNMT.gen_xml(cnmtNCA, outf)
        
        with open(os.path.join(cnmtDir, 'Header.bin'), 'rb') as ncaHd:
            mKeyRev = str(read_u8(ncaHd, 0x220))
        rightsID = '%s%s%s' % (tid, (16-len(mKeyRev))*'0', mKeyRev)
        
        
        tikPath = os.path.join(gameDir, '%s.tik' % rightsID)
        certPath = os.path.join(gameDir, '%s.cert' % rightsID)
        if CNMT.type == 'Application' or CNMT.type == 'AddOnContent':
            shutil.copy(os.path.join(os.path.dirname(__file__), 'Certificate.cert'), certPath)
            
            if tkey != '':
                with open(os.path.join(os.path.dirname(__file__), 'Ticket.tik'), 'rb') as intik:
                    data = bytearray(intik.read())
                    data[0x180:0x190] = uhx(tkey)
                    data[0x285] = int(mKeyRev)
                    data[0x2A0:0x2B0] = uhx(rightsID)
                
                    with open(tikPath, 'wb') as outtik:
                        outtik.write(data)
                print('\t\tGenerated %s and %s!' % (os.path.basename(certPath), os.path.basename(tikPath)))
            else:
                print('\t\tGenerated %s!' % os.path.basename(certPath))
        elif CNMT.type == 'Patch':
            print('\tDownloading cetk...')
            
            with open(download_cetk(rightsID, os.path.join(gameDir, '%s.cetk' % rightsID)), 'rb') as cetk:
                cetk.seek(0x180)
                tkey = hx(cetk.read(0x10)).decode()
                print('\t\tTitlekey: %s' % tkey)
                
                with open(tikPath, 'wb') as tik:
                    cetk.seek(0x0)
                    tik.write(cetk.read(0x2C0))
                    
                with open(certPath, 'wb') as cert:
                    cetk.seek(0x2C0)
                    cert.write(cetk.read(0x700))
                    
            print('\t\tExtracted %s and %s from cetk!' % (os.path.basename(certPath), os.path.basename(tikPath)))
        
    NCAs = {}
    for type in [0, 3, 4, 5, 1, 2, 6]: # Download smaller files first
        for ncaID in CNMT.parse(CNMT.ncaTypes[type]):
            print('\tDownloading %s entry (%s.nca)...' % (CNMT.ncaTypes[type], ncaID))
            url = 'https://atum%s.hac.%s.d4c.nintendo.net/c/c/%s?device_id=%s' % (n, env, ncaID, did)
            fPath = os.path.join(gameDir, ncaID + '.nca')
            NCAs.update({type: download_file(url, fPath)})
    
    if nspRepack == True:
        files = []
        files.append(certPath)
        if tkey != '':
            files.append(tikPath)
        for key in [1, 5, 2, 4, 6]:
            try:
                files.append(NCAs[key])
            except KeyError:
                pass
        files.append(cnmtNCA)
        files.append(cnmtXML)
        try:
            files.append(NCAs[3])
        except KeyError:
            pass
        
        return files
    
def download_game(tid, ver, tkey='', nspRepack=False):
    if tid.endswith('000'):   # Base game
        gameDir = os.path.join(os.path.dirname(__file__), tid)
    elif tid.endswith('800'): # Update
        basetid = '%s000'%tid[:-3]
        gameDir = os.path.join(os.path.dirname(__file__), basetid, tid, ver)
    elif not tid.endswith('00'):
        basetid = '%016x' % (int(tid, 16) - 0x1000 & 0xFFFFFFFFFFFFF000)
        gameDir = os.path.join(os.path.dirname(__file__), basetid, tid)
    else:
        print('\tInvalid shogun TitleID %s!' % tid)
        return
    os.makedirs(gameDir, exist_ok=True)
    
    if tid.endswith('800') and ver == 0:
        url = 'https://tagaya.hac.%s.eshop.nintendo.net/tagaya/hac_versionlist' % env
        r = make_request('GET', url)
        j = r.json()
    
        n = 0
        for game in j['titles']:
            n += 1
            if updateTid in game['id']:
                ver = game['version']
                break
    
        if n == len(j['titles']):
            raise ValueError('\t%s has no update available!' % updateTid)
    
    
    files = download_title(gameDir, tid, ver, tkey, nspRepack)
    
    if nspRepack == True:
        print('Creating NSP. Please wait...')

        if not tid.endswith('00'):
            ttype = 'DLC'
        elif tid.endswith('000'):
            ttype = 'GAME'
        elif tid.endswith('800'):
            ttype = 'UPDATE'
        else:
            ttype = 'UNKWN'

        outf = os.path.join(gameDir, '%.34s [%s][%s].nsp' % (title_name, ttype, tid))
        NSP = nsp(outf, files)
        NSP.repack()
    
    return gameDir
    
def download_sysupdate(ver):
    if ver == '0':
        url = 'https://sun.hac.%s.d4c.nintendo.net/v1/system_update_meta?device_id=%s' % (env, did)
        r = make_request('GET', url)
        j = r.json()
        ver = str(j['system_update_metas'][0]['title_version'])
    
    sysupdateDir = os.path.join(os.path.dirname(__file__), '0100000000000816', ver)
    os.makedirs(sysupdateDir, exist_ok=True)
    
    url = 'https://atumn.hac.%s.d4c.nintendo.net/t/s/0100000000000816/%s?device_id=%s' % (env, ver, did)
    r = make_request('HEAD', url)
    
    cnmtID = r.headers.get('X-Nintendo-Content-ID')
    print('\nDownloading CNMT (%s)...' % cnmtID)
    url = 'https://atumn.hac.%s.d4c.nintendo.net/c/s/%s?device_id=%s' % (env, cnmtID, did)
    fPath = os.path.join(sysupdateDir, '%s.cnmt.nca' % cnmtID)
    cnmtNCA = download_file(url, fPath)
    dir = decrypt_NCA(cnmtNCA)
    CNMT = cnmt(os.path.join(dir, 'section0', os.listdir(os.path.join(dir, 'section0'))[0]))
    
    titles = CNMT.parse()
    for title in titles:
        dir = os.path.join(sysupdateDir, title)
        os.makedirs(dir, exist_ok=True)
        download_title(dir, title, titles[title][0], n='n')
        
    return sysupdateDir
    
class cnmt:
    def __init__(self, fPath):
        self.packTypes = {0x1: 'SystemProgram',
                          0x2: 'SystemData',
                          0x3: 'SystemUpdate',
                          0x4: 'BootImagePackage',
                          0x5: 'BootImagePackageSafe',
                          0x80:'Application',
                          0x81:'Patch',
                          0x82:'AddOnContent',
                          0x83:'Delta'}
                          
        self.ncaTypes = {0:'Meta', 1:'Program', 2:'Data', 3:'Control', 
                         4:'HtmlDocument', 5:'LegalInformation', 6:'DeltaFragment'}
                    
        f = open(fPath, 'rb')
        
        self.path = fPath
        self.type = self.packTypes[read_u8(f, 0xC)]
        self.id = '0%s' % format(read_u64(f, 0x0), 'x')
        self.ver = str(read_u32(f, 0x8))
        self.sysver = str(read_u64(f, 0x28))
        self.dlsysver = str(read_u64(f, 0x18))
        self.digest = hx(read_at(f, f.seek(0, 2)-0x20, f.seek(0, 2))).decode()
        
        f.close()

    def parse(self, ncaType=''):
        f = open(self.path, 'rb')
        
        data = {}
        if self.type == 'SystemUpdate':
            EntriesNB = read_u16(f, 0x12)
            for n in range(0x20, 0x10*EntriesNB, 0x10):
                tid  = hex(read_u64(f, n))[2:]
                if len(tid) != 16:
                    tid = '%s%s' % ((16-len(tid))*'0',  tid)
                ver  = str(read_u32(f, n+0x8))
                packType = self.packTypes[read_u8(f, n+0xC)]
                
                data[tid] = ver, packType
        else:
            tableOffset = read_u16(f,0xE)
            contentEntriesNB = read_u16(f, 0x10)
            cmetadata = {}
            for n in range(contentEntriesNB):
                offset = 0x20 + tableOffset + 0x38*n
                hash = hx(read_at(f, offset, 0x20)).decode()
                tid  = hx(read_at(f, offset+0x20, 0x10)).decode()
                size = str(read_u48(f, offset+0x30))
                type = self.ncaTypes[read_u16(f, offset+0x36)]
                
                if type == ncaType or ncaType == '':
                    data[tid] = type, size, hash
    
        f.close()
        return data
     
    def gen_xml(self, ncaPath, outf):
        data = self.parse()
        hdPath = os.path.join(os.path.dirname(ncaPath),
                 '%s.cnmt' % os.path.basename(ncaPath).split('.')[0], 'Header.bin')
        with open(hdPath, 'rb') as ncaHd:
            mKeyRev = str(read_u8(ncaHd, 0x220))
            
        ContentMeta = ET.Element('ContentMeta')
        
        ET.SubElement(ContentMeta, 'Type').text                          = self.type
        ET.SubElement(ContentMeta, 'Id').text                            = '0x%s' % self.id
        ET.SubElement(ContentMeta, 'Version').text                       = self.ver
        ET.SubElement(ContentMeta, 'RequiredDownloadSystemVersion').text = self.dlsysver
        
        n = 1
        for tid in data:
            locals()["Content"+str(n)] = ET.SubElement(ContentMeta, 'Content')
            ET.SubElement(locals()["Content"+str(n)], 'Type').text          = data[tid][0]
            ET.SubElement(locals()["Content"+str(n)], 'Id').text            = tid
            ET.SubElement(locals()["Content"+str(n)], 'Size').text          = data[tid][1]
            ET.SubElement(locals()["Content"+str(n)], 'Hash').text          = data[tid][2]
            ET.SubElement(locals()["Content"+str(n)], 'KeyGeneration').text = mKeyRev
            n += 1
            
        # cnmt.nca itself
        cnmt = ET.SubElement(ContentMeta, 'Content')
        ET.SubElement(cnmt, 'Type').text = 'Meta'
        ET.SubElement(cnmt, 'Id').text   = os.path.basename(ncaPath).split('.')[0]
        ET.SubElement(cnmt, 'Size').text = str(os.path.getsize(ncaPath))
        hash = sha256()
        with open(ncaPath, 'rb') as nca:
            hash.update(nca.read()) # Buffer not needed
        ET.SubElement(cnmt, 'Hash').text          = hash.hexdigest()
        ET.SubElement(cnmt, 'KeyGeneration').text = mKeyRev
            
        ET.SubElement(ContentMeta, 'Digest').text                = self.digest
        ET.SubElement(ContentMeta, 'KeyGenerationMin').text      = mKeyRev
        ET.SubElement(ContentMeta, 'RequiredSystemVersion').text = self.sysver
        if self.id.endswith('800'):
            ET.SubElement(ContentMeta, 'PatchId').text = '0x%s000' % self.id[:-3]
        else:    
            ET.SubElement(ContentMeta, 'PatchId').text = '0x%s800' % self.id[:-3]
        
        string = ET.tostring(ContentMeta, encoding='utf-8')
        reparsed = minidom.parseString(string)
        with open(outf, 'w') as f:
            f.write(reparsed.toprettyxml(encoding='utf-8', indent='  ').decode()[:-1])
            
            
        print('\t\tGenerated %s!' % os.path.basename(outf))
        return outf

class nsp:
    def __init__(self, outf, files):
        self.path = outf
        self.files = files
        
    def repack(self):
        files = self.files
        hd = self.gen_header(len(files), files)
        
        outf = open(self.path, 'wb')
        outf.write(hd)
        for f in files:
            with open(f, 'rb') as inf:
                while True:
                    buf = inf.read(4096)
                    if not buf:
                        break
                    outf.write(buf)
    
        print('\tRepacked to ' + outf.name + '!')
        outf.close()
        
    def gen_header(self, filesNb, files):
        stringTable = '\x00'.join(os.path.basename(file) for file in files)
        headerSize = 0x10 + (filesNb)*0x18 + len(stringTable)
        remainder = 0x10 - headerSize%0x10
        headerSize += remainder
        
        fileSizes = [os.path.getsize(file) for file in files]
        fileOffsets = [sum(fileSizes[:n]) for n in range(filesNb)]
        
        fileNamesLengths = [len(os.path.basename(file))+1 for file in files] # +1 for the \x00
        stringTableOffsets = [sum(fileNamesLengths[:n]) for n in range(filesNb)]
        
        header =  b''
        header += b'PFS0'
        header += pk('<I', filesNb)
        header += pk('<I', len(stringTable)+remainder)
        header += b'\x00\x00\x00\x00'
        for n in range(filesNb):
            header += pk('<Q', fileOffsets[n])
            header += pk('<Q', fileSizes[n])
            header += pk('<I', stringTableOffsets[n])
            header += b'\x00\x00\x00\x00'
        header += stringTable.encode()
        header += remainder * b'\x00'
        
        return header
  
def main():
    formatter = lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=40)
    parser = argparse.ArgumentParser(formatter_class=formatter)
    
    # XXX: BROKEN. Shogun always 403s now
    #parser.add_argument('-i', dest='info', default=[], metavar='TID', nargs='+', help='''\
#print info about a title:
#   - name from shogun
#   - available updates from versionlist''')
    
    parser.add_argument('-g', dest='games', default=[], metavar='TID-VER-TKEY', nargs='+', help='''\
download games/updates/DLC's:
   - titlekey argument is optional
   - format TitleID-Version(-Titlekey)
   - update TitleID's are the same as the base game's,
     with the three last digits replaced with '800'
   - version is 0 for base games, multiple of 65536 (0x10000) for updates''')
                    
    parser.add_argument('-s', dest='sysupdates', default=[], metavar='VER', nargs='+', help='''\
download system updates:
   - version is computed as follows (credit goes to SocraticBliss):
   - X.Y.Z-B (all decimal integers)
     => VER = X*67108864 + Y*1048576 + Z*65536 + B
           (= X*0x4000000 + Y*0x100000 + Z*0x10000 + B)
   - 0 will download the lastest update''')
   
    parser.add_argument('-r', dest='repack', action='store_true', default=False, help='''\
repack the downloaded games to nsp format
   - for non-update titles, titlekey is required to generate tik
   - will generate/download cert, tik and cnmt.xml''')
                    
    args = parser.parse_args()
    
    if args.games == [] and args.sysupdates == [] and args.info == []:
        parser.print_help()
        return 1
    
    #for tid in args.info:
    #    get_info(tid.lower())
    
    for game in args.games:
        try:
            tid, ver, tkey = game.lower().split('-')
            if len(tid) != 16:
                raise ValueError('TitleID %s is not a 16-digits hexadecimal number!' % tid)
            if len(tkey) != 32:
                raise ValueError('Titlekey %s is not a 32-digits hexadecimal number!' % tkey)
            #get_info(tid)
            download_game(tid, ver, tkey, nspRepack=args.repack)
        except ValueError:
            try:
                tid, ver = game.lower().split('-')
            except ValueError:
                print('Incorrect game argument (%s): should be formatted this way: TID-VER(-TKEY)!' % game)
                return 1
                
            if len(tid) != 16:
                raise ValueError('TitleID %s is not a 16-digits hexadecimal number!' % tid)

            #get_info(tid)
            download_game(tid, ver, nspRepack=args.repack)
        
    for ver in args.sysupdates:
        download_sysupdate(ver)
        
    print('Done!')
    return 0

if __name__ == '__main__':
    urllib3.disable_warnings()

    try:
        from tqdm import tqdm
        tqdmProgBar = True
    except ImportError:
        tqdmProgBar = False
        print('Install the tqdm library for better-looking progress bars! (pip install tqdm)')
        
    configPath = os.path.join(os.path.dirname(__file__), 'CDNSPconfig.json')
    hactoolPath, keysPath, NXclientPath, ShopNPath, reg, fw, did, env = load_config(configPath)
    
    if keysPath != '':
        keysArg = ' -k "%s"' % keysPath
    else:
        keysArg = ''
    
    
    sys.exit(main())
