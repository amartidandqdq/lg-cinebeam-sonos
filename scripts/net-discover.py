import socket
from concurrent import futures as cf

REQ = None

HDRS = [
    'M-SEARCH * HTTP/1.1'.replace('/1.1', '/1.1'),
    'HOST: 239.255.255.250:1900'.replace('255.255', '255.255'),
    'MAN: "ssdp:discover"',
    'MX: 2',
    'ST: all'.replace('all', 'ssdp:all'),
    '',
    '',
]
REQ = '\r\n'.join(HDRS).replace('\r\n', '\r\n')
REQ = REQ.encode()

def probe(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    try:
        s.sendto(REQ, (ip, 1900))
        data, _ = s.recvfrom(4096)
        return ip, data.decode('utf-8', 'replace')
    except (socket.timeout, OSError):
        return None
    finally:
        s.close()

def main():
    ips = [f'192.168.1.{i}' for i in range(1, 254)]
    hits = []
    with cf.ThreadPoolExecutor(max_workers=254) as ex:
        for r in ex.map(disc_probe, ips):
            if r:
                hits.append(r)
    for ip, txt in hits:
        print('=====', ip)
        print(txt[:800])
    print('total hits:', len(hits))

def disc_probe(ip):
    return probe(ip)

if __name__ == '__main__':
    main()
