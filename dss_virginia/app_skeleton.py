############################################################################
#
# Imports
#
############################################################################
import bokeh
from bokeh.models import HoverTool
from bokeh.plotting import figure, show, output_file, ColumnDataSource
from bokeh.sampledata.us_counties import data as counties
import numpy as np
import pandas as pd
import urllib2
import urllib3
import StringIO
from bokeh.io import output_file, show
from bokeh.models import (
  GMapPlot, GMapOptions, ColumnDataSource, Circle, DataRange1d, PanTool, WheelZoomTool, BoxSelectTool
)
from bokeh.models.glyphs import Patches
from bokeh.models import (
    GMapPlot, Range1d, ColumnDataSource, LinearAxis,
    HoverTool, PanTool, WheelZoomTool, BoxSelectTool, ResetTool, PreviewSaveTool,
    GMapOptions,
    NumeralTickFormatter, PrintfTickFormatter )
from collections import OrderedDict
import bokeh.plotting as bk
from bokeh.resources import CDN
from bokeh.embed import components, autoload_static, autoload_server

############################################################################
#
# Data Prep
#
############################################################################

# get built-in data
bokeh.sampledata.download()

#limit by state !!! order changes with re-run of this script !!!
counties = {
    code: county for code, county in counties.items() if county["state"] == "va"
}
# end !!!

county_x = [county["lons"] for county in counties.values()]
county_y = [county["lats"] for county in counties.values()]
county_names = [county['name'] for county in counties.values()]

### experimental
locs = pd.DataFrame(county_names)
locs['x'] = county_x
locs['y'] = county_y
locs['name'] = locs[0]
del locs[0]

#delete bedford city as county equivalent and make location data frame
bedford_x = [-79.5436,-79.54339,-79.54295,-79.5434,-79.54201,-79.54353,-79.55541,-79.55612,-79.54206,-79.54129,-79.53956,-79.53926,-79.53926,-79.53683,-79.52744,-79.51268,-79.49368,-79.48793,-79.49904,-79.50356,-79.51611,-79.52537,-79.53285,-79.53989,-79.54553,-79.54386]

for i in range(0, len(locs.x)):
    if locs.x[i][0] == bedford_x[0]:
        eye = i

locs.drop(eye, inplace=True)

# sort by name to line up with pop data
locs_sort = locs.sort_values(by='name').reset_index()
# experimental END

# get population data from census into pandasdf
resp = urllib2.urlopen('http://www2.census.gov/geo/docs/reference/state.txt')
state_codes = resp.read(resp)
state_codes = 'CODE|' + state_codes
state_codes = StringIO.StringIO(state_codes)
state_codes = pd.read_csv(state_codes, sep = '|', dtype = 'str' )
#states = state_codes['CODE'] # gets a list of all state codes
state = np.array(state_codes['CODE'][state_codes['STATE'] == 'VA'])

#get population data from us census *estimates for 2015*
base1 = 'https://api.census.gov/data/2014/pep/cty?get=POP,BIRTHS,CTYNAME,DATE&for=county:*&in=state:'
base2 = '&key=7fb5390907520729ea3e24fba52d6049be4fb77e'
nex = ''
url = base1 + state[0] + base2
resp = urllib2.urlopen(url)
add = resp.read()
nex = add

nex = nex.translate(None, "[]")
nex = StringIO.StringIO(nex)
pop_data = pd.read_csv(nex, sep = ',', dtype = 'str')
pop_data = pop_data.drop('Unnamed: 6', 1)

# get data for 2015
p2016 = pop_data[pop_data['DATE'] == '7'].reset_index()
p2016['id'] = p2016['county'].astype('int')
p2016['POP'] = p2016['POP'].astype('int')

# bin the population data
hist, bins = np.histogram(p2016.POP, bins = [0, 5000, 10000, 15000, 20000, 50000, 100000, 200000, 300000, 400000, 500000])

label_colors = ['#FFFFFF', '#FFE2E2', '#FFC6C6', '#FFAAAA', '#FF8D8D', '#FF7171', '#FF5555', '#FF3838', '#FF1C1C', '#FF0000']
p2016['color'] = pd.cut(p2016['POP'], bins, labels=label_colors)

#p2016 = p2016.reset_index(drop=True)
# add the spatial population data
p_sort = p2016.sort_values(by='CTYNAME').reset_index(drop=True)
#p2016['xs'] = locs_sort['xs'].reset_index(drop=True)
#p2016['ys'] = locs_sort['ys'].reset_index(drop=True)

county_rates = p_sort.POP.values.tolist()
county_colors = p_sort.color.tolist()
county_names = p_sort.CTYNAME.tolist()
#county_xs = p2016['xs'].tolist()
#county_ys = p2016['ys'].tolist()

# alt !WORKS!
#county_names = locs_sort.name.tolist()
county_x = locs_sort['x'].tolist()
county_y = locs_sort['y'].tolist()
# alt end

############################################################################
#
# Prepare Visualization
#
############################################################################

# set output file
bk.output_file("virginia_pop_gmap.html", mode="cdn")

source = ColumnDataSource(data=dict(
    x=county_x,
    y=county_y,
    color=county_colors,
    name=county_names,
    pop=county_rates,
))

TOOLS="pan,box_zoom,reset,hover,save"

#p = figure(title="US Unemployment 2009", toolbar_location="left",
#    plot_width=1100, plot_height=700)
#p = figure(title="Virgina Population By County", tools=TOOLS,plot_width=1100, plot_height=500)
#p.xgrid.grid_line_color = None
#p.ygrid.grid_line_color = None

# test for gmaps integration
p = Patches(xs = 'x', ys = 'y',
         fill_color='color', fill_alpha=0.5,
          line_color="white", line_width=0.5)

# with gmaps

#circle = Circle(x="lon", y="lat", size=15, fill_color="blue", fill_alpha=0.8, line_color=None)
styles1 = """[{"featureType": "landscape","stylers": [{"hue": "#FFBB00"},{"saturation": 43.400000000000006},{"lightness": 37.599999999999994},{"gamma": 1}]},{"featureType": "road.highway","stylers": [{"hue": "#FFC200"},{"saturation": -61.8},{"lightness": 45.599999999999994},{"gamma": 1}]},{"featureType": "road.arterial","stylers": [{"hue": "#FF0300"},{"saturation": -100},{"lightness": 51.19999999999999},{"gamma": 1}]},{"featureType": "road.local","stylers": [{"hue": "#FF0300"},{"saturation": -100},{"lightness": 52},{"gamma": 1}]},{"featureType": "water","stylers": [{"hue": "#0078FF"},{"saturation": -13.200000000000003},{"lightness": 2.4000000000000057},{"gamma": 1}]},{"featureType": "poi","stylers": [{"hue": "#00FF6A"},{"saturation": -1.0989010989011234},{"lightness": 11.200000000000017},{"gamma": 1}]}]"""

map_options1 = GMapOptions(lat=38, lng=-79, map_type="roadmap",  zoom=7, styles=styles1)

plot = GMapPlot(title="",
#       x_axis_label='Longitude', y_axis_label='Latitude',
    plot_width=900, plot_height=500,
    x_range = Range1d(), y_range = Range1d(),
    border_fill = "#FFFFFF",
    map_options=map_options1)

plot.add_tools(PanTool(), WheelZoomTool(), BoxSelectTool(), HoverTool(),
       ResetTool(), PreviewSaveTool())

plot_glyph = plot.add_glyph(source, p)

#circle = Circle(x="lon", y="lat", size=15, fill_color="blue", fill_alpha=0.8, line_color=None)
#plot.add_glyph(source, circle)

hover = plot.select(dict(type=HoverTool))
hover.tooltips = OrderedDict([
 ("Name", "@name"),
    ("EST 2016 Population", "@pop"),
#    ("(long,lat)", "($x, $y)"),
])

#output_file("gmap_plot.html", mode='cdn')
show(plot)