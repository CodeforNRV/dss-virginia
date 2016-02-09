import urllib3
import certifi
from bs4 import BeautifulSoup
import re
import geopy
import json

# a few handy url generator funcitons
base_url = lambda start_num=1: "https://www.dss.virginia.gov/facility/search/cc.cgi?rm=Search;search_require_client_code-2106=1;search_require_client_code-2105=1;search_require_client_code-2102=1;search_require_client_code-2104=1;search_require_client_code-2201=1;search_require_client_code-2101=1;Start={start_num}".format(start_num=start_num)
loc_url = lambda loc_id: "https://www.dss.virginia.gov/facility/search/cc.cgi?rm=Details;ID={loc_id}".format(loc_id=loc_id)
insp_url = lambda inspection_id, loc_id: "https://www.dss.virginia.gov/facility/search/cc.cgi?rm=Inspection;Inspection={inspection_id};ID={loc_id}".format(inspection_id=inspection_id, loc_id=loc_id)

http = urllib3.PoolManager(
    cert_reqs='CERT_REQUIRED',  # Force certificate check.
    ca_certs=certifi.where(),  # Path to the Certifi bundle.
)


def get_page(url):
    '''Get all of our page data in a consistent fashion'''

    r = http.request('GET', url)
    # lxml is much better than stock python parser
    return BeautifulSoup(r.data, 'lxml')


def get_key(tag):
    '''a lot of time we will need to extract a key from a tag'''
    return tag.get_text().strip().strip(':').lower().replace(' ', '_').encode('ascii', 'ignore')


def get_loc_ids(start_num=1):
    '''Location id Generator function.
    This will automatically handeling paging of main id lookup, but you can skip ahead by passing in an in representing the ids place in global list, 1 based index'''

    done = False
    while not done:
        print 'Fetching some location ids'
        soup = get_page(base_url(start_num))

        num_locs = int(re.search('\t(\d{1,9}) records', soup.find_all('table')[1].find_all('td')[1].text).group(1))

        ids = ([int(re.search(';ID=(\d{1,9});', a['href']).group(1)) for a in soup.find_all('table')[3].find_all('a')])

        for loc_id in ids:
            start_num += 1
            yield loc_id

        if start_num >= num_locs:
            done = True


def parse_loc(loc_id):
    '''Fetch detailed info for a single location based on id'''

    # Define geolocator from GooglemapsV3 api :: no key required :: output projection EPSG:3857 Spherical Mercator (Web Mercator)
    geolocator = geopy.geocoders.GoogleV3(domain='maps.googleapis.com')

    print "Fetching info for location id =", loc_id

    soup = get_page(loc_url(loc_id))

    location_info = {
        '_type': 'location_info',
        'id': loc_id
    }

    # big breakdowns go by tables
    basic_info, additional_info, inspection_info = soup.find_all('table')[:3]

    # first table has a bunch of data in fairly unstructured format
    name_and_address, city_zip, phone_number = basic_info.find_all('tr')
    parsed_name_address = [line.strip() for line in name_and_address.get_text().split('\n') if line.strip()]
    location_info.update({
        'name': parsed_name_address[0],
        'street_address': '\n'.join(parsed_name_address[1:])
    })

    city, state_zip = city_zip.get_text().split(',')
    state, zip_code = state_zip.split()

    # Get address for geolocator with city, state and without \n
    gcode_address = ' '.join([' '.join(parsed_name_address[1:]), city.strip(), state])

    # geolocate
    location = geolocator.geocode(gcode_address)

    # update location info with lat lon and full mapped address
    location_info.update({
        'city': city.strip(),
        'state': state,
        'zip_code': zip_code,
        'phone_number': phone_number.get_text().strip(),
        'mapped_address': location.address,
        'latitude': location.latitude,
        'longitude': location.longitude
    })
    # end update

    # there are a lot of additional info that follows the general format of <td>key</td><td>value</td>
    # but some need some extra parsing
    extra_parsing = {
        'ages': lambda ages: ages.replace('\t', '').replace('\n', ''),
        'inspector': lambda inspector_info: [line.strip() for line in inspector_info.split('\n') if line.strip()]
    }
    for row in additional_info.find_all('tr')[:-1]:
        key = get_key(row.find_all('td')[0])
        val = row.find_all('td')[1].get_text().strip()
        if key in extra_parsing:
            val = extra_parsing[key](val)

        location_info.update({key: val})

    if 'inspector' in location_info:
        location_info.update({
            'inspector_name': location_info['inspector'][0],
            'inspector_phone': location_info['inspector'][1]
        })
        del location_info['inspector']

    inspection_ids = [int(re.search(';Inspection=(\d{1,6});', tag.a['href']).group(1)) for tag in inspection_info.table.find_all('tr')[1:]]

    location_info['inspections'] = [parse_inspection(insp_id, loc_id) for insp_id in inspection_ids]

    return location_info


def parse_inspection(insp_id, loc_id):
    '''To get inspection data, you need to give the site both the inspection id and location id'''

    print " Fetching info for inspection id =", insp_id

    soup = get_page(insp_url(insp_id, loc_id))

    inspection_info = {
        '_type': 'inspection_info',
        'id': insp_id,
        'loc_id': loc_id
    }

    # there is some redundant info about location, then some relevant stuff
    date, complaint = soup.find('div', id='main_content').find_all('p')[3:5]
    inspection_info.update({
        'date': date.get_text().split('\n')[5].strip(),
        'complaint': complaint.get_text().split('\n')[3].strip()
    })

    # we will need a lot of specialized parsers
    def parse_violations(violations):

        parsers = {
            'standard_#': lambda val: val.strip(),
            'description': lambda val: val.strip().replace('\r', '\n'),
            'complaint_related': lambda val: val.strip(),
            'action_to_be_taken': lambda val: val.strip().replace('\r', '\n')
        }
        line_num = 0
        violation_lines = violations.find_all('tr')
        violations_info = []
        violation_info = {}

        while line_num < len(violation_lines):

            if violation_lines[line_num].td is None:
                # there seems to be blank lines after 'complain_related' that don't have <td>s
                pass

            elif violation_lines[line_num].hr:
                violations_info.append(violation_info)
                violation_info = {}

            else:
                raw_key, val = violation_lines[line_num].get_text().split(':', 1)
                key = raw_key.strip().strip(':').lower().replace(' ', '_').encode('ascii', 'ignore')
                violation_info[key] = parsers[key](val)

            line_num += 1

        return violations_info

    parsers = {
        'areas_reviewed': lambda areas_reviewed: [areas_reviewed.br.previousSibling.strip()] + [foo.nextSibling.strip() for foo in areas_reviewed.find_all('br')],
        'technical_assistance': lambda technical_assistance: technical_assistance.get_text().strip(),
        'comments': lambda comments: comments.get_text().strip().replace('\r', '\n'),
        'violations': parse_violations
    }

    # also have a variable number of tables, id'd by <dt>s
    table_ids = [get_key(tag) for tag in soup.find_all('dt')]

    for key, tag in zip(table_ids, soup.find_all('table')[:len(table_ids)]):
        inspection_info[key] = parsers[key](tag)

    return inspection_info

# function returns census fip for given lat / lon
# not run: define example lat/lons
#latlon = [[37.23546234, -81.492883], [37.09529495, -81.59387503], [38.763819, -77.44133099999999]]

# Inputs list of latlon pairs, outputs full FIPS census code
def get_fips(latlon):
    fips = []
    http = urllib3.PoolManager()
    for i in range(0,len(latlon)):
        url = 'http://www.data.fcc.gov/api/block/find?format=json&latitude={lat}&longitude={lon}'.format(lat=latlon[i][0], lon=latlon[i][1])
        resp = http.request('GET', url)
        add = json.loads(resp.data.decode('utf8'))
        fips.append(add['Block']['FIPS'])
    return(fips)