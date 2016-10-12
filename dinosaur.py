from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import os
import json, requests, sys, random
from sqlite3 import dbapi2 as sqlite3
from wtforms import RadioField, SubmitField,IntegerField,TextAreaField
from flask_wtf import Form
import urllib.request
from flask_googlemaps import GoogleMaps # https://pypi.python.org/pypi/Flask-GoogleMaps/
from flask_googlemaps import Map, icons
import geocoder # https://pypi.python.org/pypi/geocoder
import pycountry # https://pypi.python.org/pypi/pycountry
import pywikibot # https://www.mediawiki.org/wiki/Manual:Pywikibot/Installation

# ORM - object relational mapping
# SQl Alchemy

app = Flask(__name__)

# WORKFLOW
# 1) User enters an address/location
# 2) Program turns 1) into lat/long
# 3) Program queries PaleoBioDB for fossils found within X miles of 2)
# 4) Program stores response from 3) and sends relevant data to Google Maps to create a map of fossils near you
# 5) Program queries Wikipedia and similaar sources for images and text about taxons found.

# Load default config and override config from an environment variable
app.config.update(dict(
    DATABASE=os.path.join(app.root_path, 'paleozoic.db'),
    DEBUG=True,
    SECRET_KEY='development key',
))
app.config.from_envvar('DINOSAUR_SETTINGS', silent=True)

# Initialize GoogleMaps extension
# Pass API key to Google Maps
google_maps_api_key = open('static/secret/google_maps_api_key.txt').read()
GoogleMaps(app, key=google_maps_api_key)


def connect_db():
    """Connects to the specific database."""
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def init_db():
    """Initializes the database."""
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    init_db()
    print('Initialized the database.')


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()

def add_fossildata_to_db(lat,long,taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus,nation,state,county,geologicAge,paleoenv,max_ma,min_ma,geocomments):
    db = get_db()
    data = [lat,long,taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus,nation,state,county,geologicAge,paleoenv,max_ma,min_ma,geocomments]
    db.execute('insert into fossils (lat, long, taxonName, trank_phylum, trank_class, trank_order, trank_family, trank_genus, nation, state, county, geologicAge, paleoenv, max_ma, min_ma, geocomments) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', data)
    db.commit()
    # TODO useful additions: env (paleoenvironment, which can narrow down marine/terrestrial), and (phl, cll, odl, fml), which is phylum class order family and can (frex) narrow down or eliminate non-chordates or group trilobites, which are a class and not a genus. And ggc, which is "Additional comments about the geographic location of the collection." max_ma and min_ma correspond to 'eag' and 'lag,' the "early and late bounds of the geologic time range associated with this occurrence (in Ma)"

def clear_db():
    db = get_db()
    db.execute('DELETE FROM fossils')
    db.commit()

class Fossil():
    def __init__(self, fossilName, taxonomy, location, age, coordinatePairs, paleoenv, geocomments):
        self.fossilName = fossilName
        self.taxonomy = taxonomy
        self.location = location
        self.age = age
        self.coordinatePairs = coordinatePairs
        self.paleoenv = paleoenv
        self.geocomments = geocomments
        # You can now create mapflagCaption and pageText listings, and the latlonglist (coordinatePairs + mapflagCaption), using methods in this class, and call them with Fossil.method()


def create_fossil_objects():
    db = get_db()
    fossilResults = []
    for row in db.execute("SELECT * FROM fossils"):
        coordinatePairs = [row[1],row[2]] # lat/long
        taxonName = row[3]
        trank_phylum = row[4]
        trank_class = row[5]
        trank_order = row[6]
        trank_family = row[7]
        trank_genus = row[8]
        nation = getNationFromISO3166(row[9])  # replaces 2-letter country codes (ISO-3166-1 alpha-2) with English.
        state = row[10]
        county = row[11]
        geologicAge = row[12]
        paleoenv = row[13]
        max_ma = row[14]
        min_ma = row[15]
        geocomments = row[16]
        fossilName = getfossilName(taxonName, trank_phylum, trank_class, trank_order, trank_family, trank_genus) # This is the fossil's display name
        taxonomy = getTaxonomy(trank_phylum, trank_class, trank_order, trank_family, trank_genus) # This is the fossil's tree-of-life designations, to be used in behind-the-scenes filtering
        location = getLocation(nation, state, county)
        age = getGeologicAge(geologicAge, max_ma, min_ma)
        # TODO Split the constructor for the mapflag and for the page text into separate submethods
        # TODO maybe include a visual chart/representation of where the geological ages fall in relation to each other.
        # print("FOSSILNAME: " + str(fossilName))
        # print("LOCATION: " + location)
        # print("GEOLOGICAGE: " + age)
        # print("PALEOENVIRONMENT: " + str(paleoenv))
        # print("GEOCOMMENTS: " + str(geocomments))
        newFossil = Fossil(fossilName,taxonomy,location,age,coordinatePairs,paleoenv,geocomments)
        fossilResults.append(newFossil)
    return fossilResults

def get_latlong_list(latlonglist): # TODO AFAIK this has been completely replaced by the Fossil objects and fossilResults list
    db = get_db()
    fossilResults = []
    for row in db.execute("SELECT * FROM fossils"):
        # Just lat/long: coordinatePairs = [row[1],row[2]]
        fossilName = captionConstructor(row)['fossilName']
        location = captionConstructor(row)['location']
        age = captionConstructor(row)['age']
        coordinatePairs = [row[1],row[2]] # Text popup flag
        mapflagCaption = "<b style='color:red;'>" + fossilName + "</b>. " + location + ". " + age + "."
        print("CAPTION: " + mapflagCaption)
        coords_and_mapFlag = [row[1],row[2],mapflagCaption] # Text popup flag
        # Full HTML flag: coordinatePairs = [row[1],row[2],("Hello I am <b style='color:#ffcc00;'> YELLOW </b>!" "<h2>It is HTML title</h2>" "<img src='//placehold.it/50'>""<br>Images allowed!")]
        print ("coords_and_mapFlag: " + str(coords_and_mapFlag))
        latlonglist.append(coords_and_mapFlag)
    return latlonglist

def getNationFromISO3166(nation):
    if (nation == None):
        nation = "Location undisclosed"
    elif (nation == 'UK'):
        nation = "Great Britain"
    elif (nation == 'TU'):
        nation = "Tuva (Russian Federation)"
    elif (nation == 'AA'):
        nation = "Antarctica"
    else:
        thisIsTheNation = pycountry.countries.get(alpha2=nation)
        nation = thisIsTheNation.name
    return nation

def getLocation(nation,state,county):
    if (nation == 'Great Britain'):
        if (state == None):
            location = 'Great Britain'
        elif (state == 'England' or 'Scotland' or 'Wales' or 'Northern Ireland'):
            if (county == None):
                location = state
            else:
                location = (county + ", " + state)
        else:
            if (county == None):
                location = (state + ", " + nation)
            else:
                location = (county + ", " + state + ", " + nation)
    elif (nation == 'United States'):
        if (county == None):
            location = state
        else:
            location = (county + ", " + state)
    elif (nation == None):
        nation = "Location undisclosed"
    elif (state == None):
        location = nation
    elif (county == None):
        location = (state + ", " + nation)
    else:
        location = (county + ", " + state + ", " + nation)
    return location

def getfossilName(taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus):
    if (trank_class == 'Trilobita'):
        if (trank_genus == None):
            fossilName = "Trilobite (genus " + taxonName + ")"
        elif (taxonName == None):
            fossilName = "Trilobite (genus unidentified)"
        else:
            fossilName = "Trilobite (genus " + trank_genus + ")"
    elif (trank_genus == None):
        fossilName = taxonName
    elif (taxonName == None):
        fossilName = "Unknown species"
    else:
        fossilName = trank_genus
    if fossilName == None:
        fossilName = "Species not recorded" # TODO Filter these listings out of the results.
    return fossilName

def getTaxonomy(trank_phylum, trank_class, trank_order, trank_family, trank_genus):
    taxonomy = {'phylum': trank_phylum, 'class': trank_class, 'order': trank_order, 'family': trank_family, 'genus': trank_genus}
    return taxonomy

def getGeologicAge(geologicAge,max_ma,min_ma):
    # TODO Rewrite this so that 1) It rounds to 2 decimal places and 2) If less than 1 mya, it should display as thousands instead
    if (geologicAge == None):
        age = "Geologic age unknown"
    elif (max_ma != None and min_ma != None):
        age = geologicAge + " (approx. " + str((max_ma+min_ma)/2) + " million years ago)"
    elif (max_ma != None and min_ma == None):
        age = geologicAge + " (approx. " + str(max_ma) + " million years ago)"
    else:
        age = geologicAge
        # TODO Import this list https://paleobiodb.org/data1.2/intervals/list.txt?scale=1 as a second SQLite table and use it to match the max_ma/min_ma numbers to a scale_level 2/3/4 string.
    return age

def captionConstructor(row): # TODO I think this entire function is being subsumed by the Fossil class
    taxonName = row[3]
    trank_phylum = row[4]
    trank_class = row[5]
    trank_order = row[6]
    trank_family = row[7]
    trank_genus = row[8]
    nation = getNationFromISO3166(row[9]) # replaces 2-letter country codes (ISO-3166-1 alpha-2) with English.
    state = row[10]
    county = row[11]
    geologicAge = row[12]
    paleoenv = row[13]
    max_ma = row[14]
    min_ma = row[15]
    geocomments = row[16]
    fossilName = getfossilName(taxonName, trank_phylum, trank_class, trank_order, trank_family, trank_genus)
    location = getLocation(nation,state,county)
    age = getGeologicAge(geologicAge,max_ma,min_ma)
    # TODO Split the constructor for the mapflag and for the page text into separate submethods
    # TODO maybe include a visual chart/representation of where the geological ages fall in relation to each other.
    print("fossilName: " + str(fossilName))
    print ("LOCATION: " + location)
    print ("GEOLOGICAGE: " + age)
    return {'fossilName': fossilName, 'location': location, 'age': age}


@app.route('/')
def start_here():
    name = "Zoe and Beatrice" # TODO Placeholder so I don't have to enter a name each time I restart the page
    if (name == None):
        getName()
    return render_template('home.html', name=name, searchresults=None)

@app.route('/getname')
def getName():
    name = request.args.get('getname')
    return render_template('home.html', name=name, searchresults=None)

def paleoSearch(paleobiodbURL,searchRadius):
    clear_db() # Cleans out old search results so that the new search begins on a fresh slate
    paleobiodbResponse = urllib.request.urlopen(paleobiodbURL)
    paleobiodbResponseJSONString = paleobiodbResponse.read().decode('UTF-8')
    paleobiodbResponseJson = json.loads(paleobiodbResponseJSONString)
    if ('warnings' in paleobiodbResponseJson):
        warning = paleobiodbResponseJson['warnings'][0]
        print(warning)
        # TODO Error if no exact search result match: "TypeError: 'Response' object is not subscriptable". Not sure why, this should be caught by the "warnings" flag...
        flash(warning + ". Please try again.")
        return redirect(url_for('start_here'))
    else:
        paleobiodbRecordsJson = paleobiodbResponseJson['records']
        ResultsFound = paleobiodbResponseJson['records_found']
        # For-loop to draw data (lat, lng, etc) out of the JSON response and create SQLite DB:
        for taxonResult in paleobiodbRecordsJson:
            lat = float(taxonResult['lat'])
            lng = float(taxonResult['lng'])
            if ('tna' in taxonResult):
                taxonName = str(taxonResult['tna'])
            else:
                taxonName = None
            if ('phl' in taxonResult):
                trank_phylum = str(taxonResult['phl'])
            else:
                trank_phylum = None
            if ('cll' in taxonResult):
                trank_class = str(taxonResult['cll'])
            else:
                trank_class = None
            if ('odl' in taxonResult):
                trank_order = str(taxonResult['odl'])
            else:
                trank_order = None
            if ('fml' in taxonResult):
                trank_family = str(taxonResult['fml'])
            else:
                trank_family = None
            if ('gnl' in taxonResult):
                trank_genus = str(taxonResult['gnl'])
            else:
                trank_genus = None
            if ('cc2' in taxonResult):
                nation = str(taxonResult['cc2'])
            else:
                nation = None
            if ('stp' in taxonResult):
                state = str(taxonResult['stp'])
            else:
                state = None
            if ('cny' in taxonResult):
                county = str(taxonResult['cny'])
            else:
                county = None
            if ('oei' in taxonResult):
                geologicAge = str(taxonResult['oei'])
            else:
                geologicAge = None
            if ('env' in taxonResult):
                paleoenv = str(taxonResult['env'])
            else:
                paleoenv = None
            if ('eag' in taxonResult):
                max_ma = str(taxonResult['eag'])
            else:
                max_ma = None
            if ('lag' in taxonResult):
                min_ma = str(taxonResult['lag'])
            else:
                min_ma = None
            if ('ggc' in taxonResult):
                geocomments = str(taxonResult['ggc'])
            else:
                geocomments = None
            add_fossildata_to_db(lat,lng,taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus,nation,state,county,geologicAge,paleoenv,max_ma,min_ma,geocomments) # For possible future expansion: Much more data than this is pulled due to the show=full setting. https://paleobiodb.org/data1.2/occs/list_doc.html
            # print (lat,lng,taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus,nation,state,county,geologicAge,paleoenv,max_ma,min_ma,geocomments)
    fossilResults = create_fossil_objects()
    markers = get_markers(fossilResults) # This will replace latlonglist
    # TODO Create GoogleMapQueryStatement from fossilResults; this replaces latlonglist, which is misnamed if it also has complex marker info which takes most of the effort of creating the GMQS. It should also have the zoomNumber
    # TODO Create pageTextList from fossilResults. bold/ital/color/links will be created on the html pages, so this needs to make the stuff that goes inside that. Also includes ResultsFound

    if (searchRadius == None):
        zoomNumber = 4
    elif (searchRadius >= 6):
        zoomNumber=6
    elif (searchRadius >= 3):
        zoomNumber = 7
    elif (searchRadius == 2):
        zoomNumber=8
    else:
        zoomNumber=9
    return {'zoomNumber': zoomNumber, 'ResultsFound': ResultsFound, 'markers': markers, 'fossilResults': fossilResults}

def get_markers(fossilResults):
    coords_and_mapFlag_List = []
    markers = {}
    for fossil in fossilResults:
        # Just lat/long: coordinatePairs = [row[1],row[2]]
        fossilName = fossil.fossilName
        taxonomy = fossil.taxonomy
        location = fossil.location
        age = fossil.age
        coordinatePairs = fossil.coordinatePairs
        mapflagCaption = "<b style='color:red;'>" + fossilName + "</b>. " + location + ". " + age + "."
        # print("CAPTION: " + mapflagCaption)
        coords_and_mapFlag = [coordinatePairs[0],coordinatePairs[1],mapflagCaption]
        # create map icon based on what the search result is - this could become complex, maybe separate out as its own method
        if (taxonomy['class'] == 'Trilobita'):
            icon = '/static/images/mapicons/trilobite.png'
        elif (taxonomy['class'] == 'Ornithischia'):
            icon = '/static/images/mapicons/stegosaurus.png'
        elif (taxonomy['order'] == 'Pterosauria'):
            icon = '/static/images/mapicons/pterodactyl.png'
        elif (taxonomy['genus'] == 'Homo'):
            icon = '/static/images/mapicons/cartoon_caveman.ico'
        else:
            icon = '/static/images/mapicons/townspeople-dinosaur-icon.png'

        icon_coords_and_mapFlag = { 'icon': icon, 'lat': coordinatePairs[0], 'lng': coordinatePairs[1], 'infobox': mapflagCaption }
        # Full HTML flag: coordinatePairs = [row[1],row[2],("Hello I am <b style='color:#ffcc00;'> YELLOW </b>!" "<h2>It is HTML title</h2>" "<img src='//placehold.it/50'>""<br>Images allowed!")]
        # print ("coords_and_mapFlag: " + str(coords_and_mapFlag))
        coords_and_mapFlag_List.append(icon_coords_and_mapFlag)
    markers = coords_and_mapFlag_List
    return markers

@app.route('/fossilsearch')
def fossilsearch(): # TODO This combines searchbytaxon and searchbylocation into a single function. ... Search restrictions (chordates, dinosaurs, etc.) must be built into the paleobiodbURL, so you'll need to construct it as a composite string. Is it possible to construct taxonquery and locationquery in the same method? Would be useful to be able to find "all sauropods in Europe," etc. If so, you could merge @app.route('/searchbytaxon') and @app.route('/searchbylocation') ... Dinosaurs + commonly accepted "relatives" = "saurischia,Ornithischia,plesiosauria,ichthyosauria,pterosauria" ... Hominids = "Hominidae" and then you'll need to pull species data from the returns if possible, so you can get "Homo habilis" etc. ... re: Chordates, would it be better to have that as the DEFAULT setting, and that way the user doesn't get a bunch of boring plants and insects all the time?
    # TODO You'll need a complex captionConstructor to direct to useful wikipedia (etc) links. Also, your layout should ideally include the Wiki page within your own document, and not send user away elsewhere.

    # TODO: Create a set of preselected searches for popular dinos/beasts, with small icons to click on
    if (request.args.get('taxonquery') or request.args.get('taxonradio')):
        if (request.args.get('taxonquery')):
            searchTaxon = request.args.get('taxonquery')
        else:
            searchTaxon = request.args.get('taxonradio')
    else:
        searchTaxon = None
    if (request.args.get('locationquery')):
        searchLocation = str(request.args.get('locationquery'))
        searchRadius = float(request.args.get('degrees'))
        latlngradiusString = getLatLongAndRadiusString(searchLocation, searchRadius)['latlngradiusString']
    else:
        searchLocation = None
        searchRadius = None
        latlngradiusString = ""
    baseNameString = getbaseNameString(searchTaxon)
    paleobiodbURL = 'https://paleobiodb.org/data1.2/occs/list.json?rowcount&level=3%s%s&show=full' % (baseNameString,latlngradiusString)
    print (paleobiodbURL)
    zoomNumber = paleoSearch(paleobiodbURL, searchRadius)['zoomNumber']
    ResultsFound = paleoSearch(paleobiodbURL, searchRadius)['ResultsFound']
    markers = paleoSearch(paleobiodbURL, searchRadius)['markers']
    fossilResults = paleoSearch(paleobiodbURL, searchRadius)['fossilResults']
    if (searchLocation == None):
        # Making centerpoint for taxonsearch map
        firstFossil = fossilResults[0]
        firstFossilCoordinatePairs = firstFossil.coordinatePairs
        centerLat = firstFossilCoordinatePairs[0] # Map centers on the first result TODO it would be better if the mapcenter averaged all coordinates and chose the middle, and adjusted zoom as necessary
        centerLng = firstFossilCoordinatePairs[1]
    else:
        centerLat = getLatLongAndRadiusString(searchLocation, searchRadius)['centerLat']
        centerLng = getLatLongAndRadiusString(searchLocation, searchRadius)['centerLng']
        searchCenter = {'icon': '/static/images/mapicons/my_house.png', 'lat': centerLat, 'lng': centerLng, 'infobox': "Your chosen <b style='color:#00cc00;'> centerpoint </b>!" "<h2>It is HTML title</h2>" "<img src='/static/images/mapicons/tardis_by_pirate_elf.gif'>""<br><a href=https://en.wikipedia.org/wiki/Main_Page target='_blank'>Images allowed!</a>"}
        markers.append(searchCenter)
    return render_template('map.html', centerLat=centerLat, centerLng=centerLng, searchTerm=searchTaxon, zoomNumber=zoomNumber, markers=markers, ResultsFound=ResultsFound, fossilResults=fossilResults)


@app.route('/searchbytaxon')
def searchbytaxon():
    searchTaxon = request.args.get('taxonquery')
    # Search paleobiodb for specific species
    paleobiodbURL = 'https://paleobiodb.org/data1.2/occs/list.json?rowcount&level=3&base_name=%s&show=full' % (searchTaxon)

    searchRadius = None
    zoomNumber = paleoSearch(paleobiodbURL,searchRadius)['zoomNumber']
    ResultsFound = paleoSearch(paleobiodbURL,searchRadius)['ResultsFound']
    markers = paleoSearch(paleobiodbURL,searchRadius)['markers']
    fossilResults = paleoSearch(paleobiodbURL,searchRadius)['fossilResults']
    # Making centerpoint for taxonsearch map
    firstFossil = fossilResults[0]
    firstFossilCoordinatePairs = firstFossil.coordinatePairs
    centerLat = firstFossilCoordinatePairs[0] # Map centers on the first result TODO it would be better if the mapcenter averaged all coordinates and chose something in the middle, and adjusted zoom as necessary
    centerLng = firstFossilCoordinatePairs[1]
    return render_template('map.html', centerLat=centerLat, centerLng=centerLng, searchTerm=searchTaxon, zoomNumber=zoomNumber, markers=markers, ResultsFound=ResultsFound, fossilResults=fossilResults)

@app.route('/searchbylocation')
def searchbylocation():
    searchLocation = str(request.args.get('locationquery'))
    searchRadius = float(request.args.get('degrees'))
    g = geocoder.google(searchLocation)
    gLatJson = g.json['lat']
    gLngJson = g.json['lng']
    latmin = gLatJson - (searchRadius/2)
    latmax = gLatJson + (searchRadius/2)
    lngmin = gLngJson - (searchRadius/2)
    lngmax = gLngJson + (searchRadius/2)
    # paleobiodbURL = 'https://paleobiodb.org/data1.2/occs/geosum.json?rowcount&level=3&show=full&lngmin=%s&lngmax=%s&latmin=%s&latmax=%s' % (lngmin,lngmax,latmin,latmax)
    paleobiodbURL = 'https://paleobiodb.org/data1.2/occs/list.json?rowcount&limit=100&level=3&show=full&lngmin=%s&lngmax=%s&latmin=%s&latmax=%s' % (lngmin,lngmax,latmin,latmax)
    # TODO List works but geosum does not. Geosum worked until I set this part up, though - why?
    zoomNumber = paleoSearch(paleobiodbURL,searchRadius)['zoomNumber']
    ResultsFound = paleoSearch(paleobiodbURL,searchRadius)['ResultsFound']
    markers = paleoSearch(paleobiodbURL,searchRadius)['markers']
    fossilResults = paleoSearch(paleobiodbURL,searchRadius)['fossilResults']
    # markers = {'/static/images/mapicons/townspeople-dinosaur-icon.png': markerCaptions}
    # markers = {'/static/images/mapicons/townspeople-dinosaur-icon.png': latlonglist, '/static/images/mapicons/my_house.png': [(gLatJson,gLngJson,("Your chosen <b style='color:#00cc00;'> centerpoint </b>!" "<h2>It is HTML title</h2>" "<img src='/static/images/mapicons/tardis_by_pirate_elf.gif'>""<br><a href=https://en.wikipedia.org/wiki/Main_Page target='_blank'>Images allowed!</a>"))]}
    searchCenter = {'icon': '/static/images/mapicons/my_house.png', 'lat': gLatJson, 'lng': gLngJson, 'infobox': "Your chosen <b style='color:#00cc00;'> centerpoint </b>!" "<h2>It is HTML title</h2>" "<img src='/static/images/mapicons/tardis_by_pirate_elf.gif'>""<br><a href=https://en.wikipedia.org/wiki/Main_Page target='_blank'>Images allowed!</a>"}
    markers.append(searchCenter)
    # TODO You'll need a complex captionConstructor to direct to useful wikipedia (etc) links. Also, your layout should ideally include the Wiki page within your own document, and not send user away elsewhere.
    return render_template('map.html', searchTerm=searchLocation, centerLat=gLatJson, centerLng=gLngJson, markers=markers, zoomNumber=zoomNumber, ResultsFound=ResultsFound, fossilResults=fossilResults)

def getbaseNameString(searchTaxon):
    # This downloads the JSON data for a species search from PaleoBioDB. "taxon_name" returns just that taxon, while "base_name" returns taxon + all subtaxa (genus/species names). Search multiple taxa with comma separator. Wildcards include %: "Stegosaur%" pulls up both Stegosaurus and Stegosauridae. https://paleobiodb.org/data1.2/general/taxon_names_doc.htm
    # Search paleobiodb for specific species
    if (searchTaxon == None):
        return ""
    else:
        baseNameString = '&base_name=' + searchTaxon
        return baseNameString

def getLatLongAndRadiusString(searchLocation,searchRadius):
    if (searchLocation == None):
        return ""
    else:
        # Geocoding an address into lat/long: https://developers.google.com/maps/documentation/javascript/geocoding (For Android, here: https://developer.android.com/training/building-location.html) A more user-friendly Python plugin is here https://pypi.python.org/pypi/geocoder
        searchLocation = str(request.args.get('locationquery'))
        searchRadius = float(request.args.get('degrees'))
        g = geocoder.google(searchLocation)
        gLatJson = g.json['lat']
        gLngJson = g.json['lng']
        latmin = gLatJson - (searchRadius/2)
        latmax = gLatJson + (searchRadius/2)
        lngmin = gLngJson - (searchRadius/2)
        lngmax = gLngJson + (searchRadius/2)
        latlngradiusString = '&lngmin=%s&lngmax=%s&latmin=%s&latmax=%s' % (lngmin,lngmax,latmin,latmax)
        # TODO How to deal with multiple results for the same latlong? The map icons will cover up most of the results. Easiest: create fuller text w/ links in the ResultsFound list that goes under the map.
        return {'latlngradiusString': latlngradiusString, 'centerLat': gLatJson, 'centerLng': gLngJson}

def getWikipedia(searchQuery):
    # Info here: https://www.mediawiki.org/wiki/API:Main_page
    # wikilinkJson = https://en.wikipedia.org/w/api.php?action=query&titles=Main%20Page&prop=revisions&rvprop=content&format=json
    # wikilinkJsonFM = https://en.wikipedia.org/w/api.php?action=query&titles=Main%20Page&prop=revisions&rvprop=content&format=jsonfm
    wikilinkJson = 'https://en.wikipedia.org/w/api.php?action=query&titles=%s&prop=revisions&rvprop=content&format=json' % (searchQuery)

    wikipediaWhatever = "SUCCESS!"
    return wikipediaWhatever

@app.route('/cancel')
def cancel():
    flash('Search canceled. Returning to start.')
    clear_db()
    return redirect(url_for('start_here'))

if __name__ == '__main__':
    app.run()
