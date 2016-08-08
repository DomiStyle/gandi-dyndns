#!/usr/bin/env python2

import json
import xmlrpclib
import os.path
import socket

import logging as log
log.basicConfig(format='%(asctime)-15s [%(levelname)s] %(message)s', level=log.DEBUG)

class GandiServerProxy(object):
  '''
  Proxy calls to an internal xmlrpclib.ServerProxy instance, accounting for the
  quirks of the Gandi API format, namely dot-delimited method names. This allows
  calling the API using Python attribute accessors instead of strings, and
  allows for the API key to be pre-loaded into all method calls.
  '''

  def __init__(self, api_key, proxy=None, chain=[], test=False):
    self.api_key = api_key
    self.chain = chain

    # create a new proxy if none was provided via chaining
    if proxy is None:
      # test and production environments use different URLs
      url = 'https://rpc.gandi.net/xmlrpc/'
      if test:
        url = 'https://rpc.ote.gandi.net/xmlrpc/'

      proxy = xmlrpclib.ServerProxy(url)

    self.proxy = proxy

  def __getattr__(self, method):
    # copy the chain with the new method added to the end
    new_chain = self.chain[:]
    new_chain.append(method)

    # return a new instance pre-loaded with the method chain so far
    return GandiServerProxy(self.api_key, self.proxy, chain=new_chain)

  def __call__(self, *args):
    '''Call the chained XMLRPC method.'''

    # build the method name and clear the chain
    method = '.'.join(self.chain)
    del self.chain[:]

    # prepend the API key to the method call
    key_args = (self.api_key,) + args

    # call the proxy's method with the modified arguments
    return getattr(self.proxy, method)(*key_args)

def load_config():
  '''Load the config file from disk.'''
  with open('config.json') as f:
    return json.load(f)

def is_valid_dynamic_record(name, record):
  '''Return True if the record matched the given name and is an A record.'''
  return record['name'] == name and record['type'].lower() == 'a'

def check_config(conf):
  '''
  Alert the user that they're using invalid config options, such as when
  breaking changes to the config are made.
  '''

  if 'name' in conf:
    log.fatal("Parameter 'name' is now named 'names' and is an array.")
    return False

  # convert old-style configuration, e.g.
  #   "domain": "example.com", "names": [ "foo", "bar", "@" ]
  # to new style:
  #   "domains": { "example.com": [ "foo", "bar", "@" ] }
  if 'domain' in conf and 'names' in conf:
    conf['domains'] = { conf.pop('domain'): conf.pop('names') }

  return True

def update_ip(external_ip):
  '''
  Check our external IP address and update Gandi's A-record to point to it if
  it has changed.
  '''

  # load the config file so we can get our variables
  log.debug('Loading config file...')
  config = load_config()
  if not check_config(config):
    sys.exit(2)
  log.debug('Config file loaded.')

  # create a connection to the Gandi production API
  gandi = GandiServerProxy(config['api_key'])

  log.debug('Updating dynamic IP: %s', external_ip)

  exit_code = 0

  for domain in config['domains']:
    # get the current zone id for the configured domain
    log.debug("Getting domain info for domain '%s'...", domain)
    domain_info = gandi.domain.info(domain)
    zone_id = domain_info['zone_id']
    log.debug('Got domain info.')

    # get the list of records for the domain's current zone
    log.debug('Getting zone records for live zone version...')
    zone_records = gandi.domain.zone.record.list(zone_id, 0)
    log.debug('Got zone records.')

    updates = []
    for rec in config['domains'][domain]:
      rec = rec.strip()

      # find the configured record, or None if there's not a valid one
      log.debug("Searching for dynamic record '%s'...", rec)
      dynamic_record = None
      for record in zone_records:
        if is_valid_dynamic_record(rec, record):
          dynamic_record = record
          break

      # fail if we found no valid record to update
      if dynamic_record is None:
        log.error('No record found - there must be an A record with a matching name.')
        continue # with next record

      log.debug('  Dynamic record found.')

      # extract the current live IP
      record_ip = dynamic_record['value'].strip()
      log.debug('  Current dynamic record IP is: %s', record_ip)

      # compare the IPs, and exit if they match
      if external_ip == record_ip:
        log.debug('  External IP matches current dynamic record IP, no update necessary.')
        continue # with next record

      log.debug('  External IP differs from current dynamic record IP!')
      updates.append(rec)

    if not updates:
      log.info('External IP matches current dynamic records IPs, no update necessary.')
      continue # with next domain

    # clone the active zone version so we can modify it
    log.info('Cloning current zone version...')
    new_version_id = gandi.domain.zone.version.new(zone_id)
    log.info('Current zone version cloned.')

    log.info('Getting cloned zone records...')
    new_zone_records = gandi.domain.zone.record.list(zone_id, new_version_id)
    log.info('Cloned zone records retrieved.')

    errors = 0
    for rec in updates:
      # find the configured record, or None if there's not a valid one
      log.debug('Locating dynamic record in cloned zone version...')
      new_dynamic_record = None
      for record in new_zone_records:
        if is_valid_dynamic_record(rec, record):
          new_dynamic_record = record
          break

      # fail if we couldn't find the dynamic record again (this shouldn't happen...)
      if new_dynamic_record is None:
        log.error('Could not find dynamic record in cloned zone version!')
        errors += 1
        continue # with next record

      log.debug('Cloned dynamic record found.')

      # update the new version's dynamic record value (i.e. its IP address)
      log.debug('Updating dynamic record with current external IP...')
      updated_records = gandi.domain.zone.record.update(zone_id, new_version_id, {
        'id': new_dynamic_record['id']
      }, {
        'name': new_dynamic_record['name'],
        'type': new_dynamic_record['type'],
        'value': external_ip
      })

      # ensure that we successfully set the new dynamic record
      if (not updated_records or
          'value' not in updated_records[0] or
          updated_records[0]['value'] != external_ip):
        log.fatal('Failed to successfully update dynamic record!')
        errors += 1
        continue # with next record

      log.info('Dynamic record updated.')

    if errors:
      log.info('Errors during processing, zone NOT UPDATED.')
      exit_code = 1
      continue # with next domain

    # set the new zone version as the active version
    log.info('Updating active zone version...')
    gandi.domain.zone.version.set(zone_id, new_version_id)
    
    log.info('Set zone %d as the active zone version.', new_version_id)
    log.info('Dynamic record successfully updated to %s!', external_ip)

  if exit_code != 0:
    sys.exit(exit_code)

def main(args):
  if not os.path.isfile('config.json'):
    log.info('No config.json found! Please rename config-example.json and adjust the file accordingly.')
    sys.exit(1)

  if len(args) > 1:
    try:
      socket.inet_aton(args[1])
      update_ip(args[1])
    except socket.error:
      log.info('No valid IP given!')
      sys.exit(1)
  else:
    log.info('No IP given as argument!')
    sys.exit(1)

if __name__ == '__main__':
  import sys
  main(sys.argv)
