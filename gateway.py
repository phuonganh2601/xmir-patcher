#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import random
import hashlib
import subprocess
import re
import requests
import telnetlib
import ftplib
import atexit


def die(*args):
  err = 1
  prefix = "ERROR: "
  msg = "<undefined>"
  if len(args) > 0:
    if isinstance(args[0], int):
      err = args[0]
    else:
      msg = args[0]
  if (err == 0):
    prefix = ""
  if len(args) > 1:
    msg = args[1]
  print(" ")
  print(prefix + msg)
  print(" ")
  sys.exit(err)

def get_http_headers():
  headers = {}
  headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
  headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0"
  return headers


class Gateway():
  verbose = 2
  timeout = 4
  config = {}
  device_name = None
  webpassword = None
  status = -2
  ftp = None
  
  def __init__(self, timeout = 4, verbose = 2, detect_device = True):
    self.verbose = verbose
    self.timeout = timeout
    self.config['device_ip_addr'] = None
    self.load_config()
    self.device_name = None
    self.webpassword = None
    self.status = -2
    atexit.register(self.cleanup)
    os.makedirs('outdir', exist_ok = True)
    os.makedirs('tmp', exist_ok = True)
    if detect_device:
      self.detect_device()

  def detect_device(self):
    self.device_name = None
    self.status = -2
    try:
      r0 = requests.get("http://{ip_addr}/cgi-bin/luci/web".format(ip_addr = self.ip_addr), timeout = self.timeout)
      r0.raise_for_status()
      #with open("r0.txt", "wb") as file:
      #  file.write(r0.text.encode("utf-8"))
      hardware = re.findall(r'hardware = \'(.*?)\'', r0.text)
      if hardware and len(hardware) > 0:
        self.device_name = hardware[0]
      else:
        hardware = re.findall(r'hardwareVersion: \'(.*?)\'', r0.text)
        if hardware and len(hardware) > 0:
          self.device_name = hardware[0]
      self.device_name = self.device_name.lower()
    except requests.exceptions.HTTPError as e:
      print("Http Error:", e)
    except requests.exceptions.ConnectionError as e:
      #print("Error Connecting:", e)
      return self.status
    except requests.exceptions.ConnectTimeout as e:
      print ("ConnectTimeout Error:", e)
    except requests.exceptions.Timeout as e:
      print ("Timeout Error:", e)
    except requests.exceptions.RequestException as e:
      print("Request Exception:", e)
    except Exception:      
      pass
    if not self.device_name:
      die("You need to make the initial configuration in the WEB of the device!")
    self.status = -1
    x = -1
    try:
      x = r0.text.find('a href="/cgi-bin/luci/web/init/hello')
    except:
      return self.status
    if (x > 10):
      self.webpassword = 'admin'
      die("You need to make the initial configuration in the WEB of the device!")
    self.status = 1
    return self.status

  def cleanup(self):
    try:
      self.ftp.quit()
    except Exception:
      pass
    try:
      self.ftp.close()
    except Exception:
      pass
    self.ftp = None

  @property
  def ip_addr(self):
    return self.config['device_ip_addr']

  @ip_addr.setter
  def ip_addr(self, value):
    self.config['device_ip_addr'] = value

  def load_config(self):
    self.config = {}
    with open('config.txt', 'r') as file:
      self.config = json.load(file)
    self.config['device_ip_addr'] = (self.config['device_ip_addr']).strip()

  def save_config(self):
    with open('config.txt', 'w') as file:
      json.dump(self.config, file, indent=4, sort_keys=True)

  def set_config_param(self, key, value):
    self.config[key] = value
    self.save_config()

  def create_telnet(self, verbose = 0):
    try:
      tn = telnetlib.Telnet(self.ip_addr)
      tn.read_until(b"login: ")
      tn.write(b"root\n")
      tn.read_until(b"Password: ")
      tn.write(b"root\n")
      tn.read_until(b"root@XiaoQiang:~#")
      return tn
    except Exception as e:
      #print(e)
      if verbose:
        die("telnet not responding (IP: {})".format(self.ip_addr))
      return None
    return tn

  def create_ftp(self, verbose = 0):
    if self.ftp and self.ftp.sock:
      try:
        self.ftp.voidcmd("NOOP")
        return self.ftp  #Already connected
      except Exception:
        pass
    self.ftp = None
    try:
      #timeout = 10 if self.timeout < 10 else self.timeout
      self.ftp = ftplib.FTP(self.ip_addr, user='root', passwd='root', timeout=self.timeout)
      self.ftp.voidcmd("NOOP")
    except Exception:
      self.ftp = None
      if verbose:
        die("ftp not responding (IP: {})".format(self.ip_addr))
      return None
    return self.ftp

  def ping(self, verbose = 2):
    tn = self.create_telnet(verbose)
    if not tn:
      return False
    ftp = self.create_ftp(verbose)
    if not ftp:
      return False
    return True

  def run_cmd(self, cmd, msg = None):
    tn = self.create_telnet(self.verbose)
    if (msg):
      print(msg)
    cmdlist = []
    if isinstance(cmd, str):      
      cmdlist.append(cmd)
    else:
      cmdlist = cmd
    for idx, cmd in enumerate(cmdlist):
      cmd = (cmd + '\n').encode('ascii')
      tn.write(cmd)
      tn.read_until(b"root@XiaoQiang:~#")
    tn.write(b"exit\n")
    return True

  def download(self, fn_remote, fn_local, verbose = 1):
    self.create_ftp(self.verbose)
    file = open(fn_local, 'wb')
    if verbose and self.verbose:
      print('Download file: "{}" ....'.format(fn_remote))
    self.ftp.retrbinary('RETR ' + fn_remote, file.write)
    file.close()
    return True

  def upload(self, fn_local, fn_remote, verbose = 1):
    try:
      file = open(fn_local, 'rb')
    except Exception:
      die('File "{}" not found.'.format(fn_local))
    self.create_ftp(self.verbose)
    if verbose and self.verbose:
      print('Upload file: "{}" ....'.format(fn_local))
    self.ftp.storbinary('STOR ' + fn_remote, file)
    file.close()
    return True


if __name__ == "__main__":
  if len(sys.argv) > 1:
    ip_addr = sys.argv[1]
    gw = Gateway(detect_device = False)
    gw.ip_addr = ip_addr
    gw.save_config()
    print("Device IP-address changed to {}".format(ip_addr))
    
