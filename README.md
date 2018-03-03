gandi_dyndns
----

### Notes

This script uses the old XML-RPC API by Gandi. If you updated your DNS records to their new LiveDNS service you need to use [this script](https://github.com/DomiStyle/gandi-live-dns) instead.

Original script by [Jason T. Bradshaw](https://github.com/jasontbradshaw). This version was modified to receive an updated IP via an CLI argument rather than depending on external services. This makes it simpler to use for Dynamic DNS setups where the router/firewall already knows the external IP address. A common setup would be a pfSense firewall with a custom Dynamic DNS provider.

This implements a simple dynamic DNS updater for the
[Gandi](https://www.gandi.net) registrar. It uses their XML-RPC API to update
the zone file for a subdomain of a domain name to point at the external IPv4
address of the computer it has been run from.

It requires a server running a reasonably recent version of Python 2. It has
been tested on Ubuntu/Arch Linux using Python 2.7.

### Walkthrough
###### Last updated August 8th, 2016.

Say you'd like to be able to access your home server externally at
`dynamic.example.com`.

#### API Key
First, you must apply for an API key with Gandi. Visit
https://www.gandi.net/admin/api_key and apply for (at least) the production API
key by following their directions. Once your request has been approved, you can
return to this page to retrieve the production API key.

#### A Record Setup
Then, you'll need to create a [DNS A
record](http://en.wikipedia.org/wiki/List_of_DNS_record_types) in the zone file
for your `example.com` domain. This is how you'll access your server over the
Internet at large!

1. Visit https://www.gandi.net/admin/domain and click on the `example.com`
   domain.
1. Click on "Edit the Zone" under "Zone files".
1. Click "Create a new version".
1. Click "Add".
1. Change the values to:

  | Field | Value
  | ----: | :----
  | Type  | A
  | TTL   | 5 minutes
  | Name  | dynamic
  | Value | 127.0.0.1

1. Click "Submit".
1. Click "Use this version".
1. Click "Submit".

#### Script Configuration
Then you'd need to configure the script.

1. Copy `config-example.json` to `config.json`, and put it in the same directory
   as the script.
1. Open it with a text editor, and change it to look like the following:

  ```json
  {
    "api_key": "yourtwentyfourcharapikey",
    "domains": { "example.com": ["dynamic"] }
  }
  ```

  You can apply for/retrieve your production API key at
  https://www.gandi.net/admin/api_key.

  If you'd like to update more than one record with the external IP, simply add
  more values to the list in the `domains` dict:

  ```json
    "domains": { "example.com": ["dynamic", "@", "mail", "xmpp"] }
  ```

  If you'd like to update multiple domains, add more keys to the `domains` dict:

  ```json
    "domains": {
      "example.com": ["dynamic"],
      "example.org": ["www"]
    }
  ```

1. Save and close the file.

#### Notes

The first time your A record is configured, it may take several hours
for the changes to propogate through the DNS system!

We set the A record's TTL to 5 minutes so that when the address is dynamically
updated by the script, that's the (hopefully) longest amount of time that would
pass before the DNS system caught up with the change. Setting this much lower
wouldn't be of much use, and could even cause DNS errors (see
http://www.zytrax.com/books/dns/info/minimum-ttl.html).

### Configuration

#### config.json
Config values for your Gandi account and domain/subdomain must be located in a
`config.json` file in the same directory as the script. `config-example.json`
contains an example configuration including all configurable options, and should
be used as a template for your personal `config.json`.

### Use
Pass an IP address to the script and it will update your records according to your config.json file.

```bash
./gandi_dyndns.py YOUR_IP_HERE
```

For usage with pfSense or any similar firewall/router with options for custom dynamic DNS providers you can use a simple PHP script like this:

```php
<?php
   if(isset($_GET['ip']) && filter_var($_GET['ip'], FILTER_VALIDATE_IP))
   {
      $output = shell_exec('./gandi_dyndns.py ' . $_GET['ip']);
      echo "OK";
   }
   else
      echo "FAIL";
?>
```

Call it from your pfSense under "Services -> Dynamic DNS":

| Field                             | Value
| ----:                             | :----
| Service Type                      | Custom
| Interface to monitor              | WAN
| Interface to send update from     | LAN (also works with WAN)
| Update URL                        | http://dyndns.example.org?ip=%IP%
| Result Match                      | OK

NOTE: dyndns.example.org points to the web server where the above PHP script and the Python script are hosted. While you can host this directly on your firewall I wouldn't recommend it.

IMPORTANT: Make sure to restrict the server where you are hosting your dynamic DNS script to only allow access from the IP of your firewall. If you can't do this because your web server is located on the WAN side you can add another HTTP parameter for a password authentication.
