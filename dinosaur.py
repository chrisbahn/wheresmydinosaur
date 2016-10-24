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
from flask_sqlalchemy import SQLAlchemy

# import pywikibot # https://www.mediawiki.org/wiki/Manual:Pywikibot/Installation

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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dinosaur.db'
db = SQLAlchemy(app)

# Initialize GoogleMaps extension
# Pass API key to Google Maps
google_maps_api_key = open('static/secret/google_maps_api_key.txt').read()
GoogleMaps(app, key=google_maps_api_key)


# TODO This function erases the ENTIRE set of SQLAFossils. You should also have functions to delete a specified subset of records.
def clear_db():
    # db = get_db()
    # db.execute('DELETE FROM fossils')
    # db.commit()
    allFossils = SQLAFossil.query.all()
    for Fossil in allFossils:
        db.session.delete(Fossil)
        db.session.commit()

class SQLAFossil(db.Model):
    # TODO These assume you have distilled the 16 JSON variables into the 7 main variables. BUT: there might be value in ALSO keeping the 16 variables on hand here. "Age" is a string, and you could do more with its three components if you retained them as separate elements. OTOH, you could maybe store "age" as a PickleType, and have a submethod that creates the "age" string... Same with "location": The separate elements could conceivably be useful, for instance you could pull all finds where state=Minnesota.
    id = db.Column(db.Integer, primary_key=True)
    # The following variables are created by manipulating or consolidating two or more of the JSON variables AND ARE currently used to create maps
    fossilName = db.Column(db.String(80))
    taxonomy = db.Column(db.PickleType)
    location = db.Column(db.String(100))
    age = db.Column(db.String(50))
    coordinatePairs = db.Column(db.PickleType)
    # The following variables are created from a single JSON variable, usually with some manipulation, AND ARE NOT currently used to create maps
    paleoenv = db.Column(db.String(30))
    geocomments = db.Column(db.String(200))
    # The following variables are used to create variables mentioned above, but but are potentially useful as singles as well. TODO location and age above should become dictionary PickleTypes including the three elements of each one, but you'll need to rewrite later calls to them, which assume they are strings.
    nation = db.Column(db.String(40))
    state = db.Column(db.String(40))
    county = db.Column(db.String(80))
    geologicAge = db.Column(db.String(30))
    max_ma = db.Column(db.Float)
    min_ma = db.Column(db.Float)

    def __init__(self, fossilName, taxonomy, location, age, coordinatePairs, paleoenv, geocomments):
        self.fossilName = fossilName
        self.taxonomy = taxonomy
        self.location = location
        self.age = age
        self.coordinatePairs = coordinatePairs
        self.paleoenv = paleoenv
        self.geocomments = geocomments


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

def paleoSearch(paleobiodbURL):
    clear_db() # Cleans out old search results so that the new search begins on a fresh slate
    paleobiodbResponse = urllib.request.urlopen(paleobiodbURL)
    paleobiodbResponseJSONString = paleobiodbResponse.read().decode('UTF-8')
    paleobiodbResponseJson = json.loads(paleobiodbResponseJSONString)
    if ('warnings' in paleobiodbResponseJson): # Catches problems like typos in dinosaur names, i.e. "tircratops"
        warning = paleobiodbResponseJson['warnings'][0]
        print(warning)
        ResultsFound = None
    else:
        warning = None
        paleobiodbRecordsJson = paleobiodbResponseJson['records']
        ResultsFound = paleobiodbResponseJson['records_found']
        for taxonResult in paleobiodbRecordsJson: # For-loop to draw just the wanted data (lat, lng, etc) out of the JSON response, filtering out blanks and other unusable data. The good data is then turned into a SQL Alchemy Fossil object
            filterPaleobiodbResponseJson(taxonResult)
            # For future expansion: JSON results contain more data about each fossil find than I'm using. See https://paleobiodb.org/data1.2/occs/list_doc.html
    allFossils = SQLAFossil.query.all()
    markers = get_markers(allFossils)
    # TODO Create pageTextList from fossilResults. bold/ital/color/links will be created on the html pages, so this needs to make the stuff that goes inside that. Also includes ResultsFound
    return {'ResultsFound': ResultsFound, 'markers': markers, 'allFossils': allFossils, 'warning': warning}

def filterPaleobiodbResponseJson(taxonResult): # TODO This needs to return data to plug back into Fossil object
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
        max_ma = float(taxonResult['eag'])
    else:
        max_ma = None
    if ('lag' in taxonResult):
        min_ma = float(taxonResult['lag'])
    else:
        min_ma = None
    if ('ggc' in taxonResult):
        geocomments = str(taxonResult['ggc'])
    else:
        geocomments = None
    create_fossil_objects(lat, lng, taxonName, trank_phylum, trank_class, trank_order, trank_family, trank_genus, nation, state, county, geologicAge, paleoenv, max_ma, min_ma, geocomments)  # Creates a SQLAFossil object

def create_fossil_objects(lat,lng,taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus,nation,state,county,geologicAge,paleoenv,max_ma,min_ma,geocomments):
    # This takes the raw JSON variables from paleobiodbRecordsJson, created in paleoSearch(), and creates a set of SQLAFossil objects for mapping, etc.
    coordinatePairs = [lat, lng]  # lat/long
    fossilName = getfossilName(taxonName, trank_phylum, trank_class, trank_order, trank_family,trank_genus)  # This is the fossil's display name
    taxonomy = getTaxonomy(trank_phylum, trank_class, trank_order, trank_family,trank_genus)  # This is the fossil's tree-of-life designations, to be used in behind-the-scenes filtering
    location = getLocation(nation, state, county, geocomments)
    age = getGeologicAge(geologicAge, max_ma, min_ma)
    # TODO Split the constructor for the mapflag and for the page text into separate submethods
    # print("FOSSILNAME: " + str(fossilName))
    # print("LOCATION: " + location)
    # print("GEOLOGICAGE: " + age)
    # print("PALEOENVIRONMENT: " + str(paleoenv))
    # print("GEOCOMMENTS: " + str(geocomments))
    newFossil = SQLAFossil(fossilName, taxonomy, location, age, coordinatePairs, paleoenv, geocomments)
    db.session.add(newFossil)
    db.session.commit()
    return newFossil # DO I NEED TO RETURN ANYTHING?

# How data flows in this program: A structured query to paleoBioDB gets back JSON data, which is then filtered into SQL ALchemy Fossil objects, which are then used to create Google Maps markers and basic display info on what the fossil is. NOTE: The set of Fossil objects is erased before each new search, in order to make it easier to handle the information. However, you could do more with your data set if you cached older searches and created a growing database. You'd need to write a method to ensure that a new JSON search would only create new Fossil objects if they didn't duplicate ones already in the system, but still display the full results of a search.


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
        print (nation)
    return nation

def getLocation(nation,state,county,geocomments):
    if (nation == None) and (state == None) and (county == None):
        if (geocomments != None):
            location = geocomments
        else:
            location = "Location undisclosed"
    else:
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
            if (state != None):
                if (county == None):
                    location = state
                else:
                    location = county + ", " + state
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
    elif (trank_class == 'Aves'):
        fossilName = "Bird (genus " + taxonName + ")"
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
    if (geologicAge == None):
        age = "Geologic age unknown"
    else:
        if (max_ma < 1):
            if (min_ma != None):
                age = geologicAge + " (approx. " + str(round(((max_ma+min_ma)/2)*1000,2)) + " thousand years ago)"
            elif (min_ma == None):
                age = geologicAge + " (approx. " + str(max_ma*1000) + " thousand years ago)"
        elif (max_ma >= 1):
            if (min_ma != None):
                    age = geologicAge + " (approx. " + str(round((max_ma+min_ma)/2,2)) + " million years ago)"
            elif (min_ma == None):
                age = geologicAge + " (approx. " + str(max_ma) + " million years ago)"
        else:
            age = geologicAge
        # TODO Import this list https://paleobiodb.org/data1.2/intervals/list.txt?scale=1 as a second table and use it to match the max_ma/min_ma numbers to a scale_level 2/3/4 string.
    return age


def get_markers(allFossils):
    coords_and_mapFlag_List = []
    markers = {}
    for fossil in allFossils:
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
        print ("PHYLUM: " + str(taxonomy['phylum']) + ", CLASS: " + str(taxonomy['class']) + ", ORDER: " + str(taxonomy['order']) + ", FAMILY: " + str(taxonomy['family']) + ", GENUS: " + str(taxonomy['genus']))
        if (taxonomy['class'] == 'Trilobita'):
            icon = '/static/images/mapicons/trilobite.png'
        elif (taxonomy['class'] == 'Saurischia'):
            if (taxonomy['family'] == 'Camarasauridae' or taxonomy['family'] == 'Brachiosauridae' or taxonomy['family'] == 'Euhelopodidae' or taxonomy['family'] == 'Titanosauridae' or taxonomy['family'] == 'Mamenchisauridae' or taxonomy['family'] == 'Diplodocidae' or taxonomy['family'] == 'Massospondylidae' or taxonomy['family'] == 'Megaloolithidae' or taxonomy['family'] == 'Riojasauridae' or taxonomy['family'] == 'Plateosauridae' or taxonomy['family'] == 'Saltasauridae' or taxonomy['family'] == 'Faveoloolithidae' or taxonomy['family'] == 'Dicraeosauridae' or taxonomy['family'] == 'Nemegtosauridae' or taxonomy['family'] == 'Rebbachisauridae'):
                icon = '/static/images/mapicons/brontosaurus.png'
            else:
                icon = '/static/images/mapicons/tyrannosaurus_rex.png'
        elif (taxonomy['class'] == 'Ornithischia'):
            if (taxonomy['order'] == 'Thyreophora'):
                icon = '/static/images/mapicons/stegosaurus.png'
            elif (taxonomy['family'] == 'Ceratopsidae'):
                icon = '/static/images/mapicons/triceratops.png'
            else:
                icon = '/static/images/mapicons/stegosaurus.png'
        elif (taxonomy['order'] == 'Pterosauria'):
            icon = '/static/images/mapicons/pterodactyl.png'
        elif (taxonomy['order'] == 'plesiosauridae' or taxonomy['order'] == 'ichthyosauridae'):
            icon = '/static/images/mapicons/plesiosaur.png'
        elif (taxonomy['family'] == 'Hominidae'):
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
def fossilsearch():
    # This downloads the JSON data for a search on PaleoBioDB. "taxon_name" returns just that taxon, while "base_name" returns taxon + all subtaxa (genus/species names). Search multiple taxa with comma separator. Wildcards include %: "Stegosaur%" pulls up both Stegosaurus and Stegosauridae. https://paleobiodb.org/data1.2/general/taxon_names_doc.htm
    searchTaxon = getSearchTaxon(request.args.get('taxonquery'), request.args.get('taxonradio'))
    baseNameString = getbaseNameString(searchTaxon)
    searchLocation = request.args.get('locationquery')
    # if (request.args.get('degrees') == None):
    #     searchRadius = 1
    # else:
    #     searchRadius = int(request.args.get('degrees'))
    searchRadius = int(request.args.get('degrees'))
    print ('searchLocation =' + str(searchLocation))
    latlngradiusString = getLatLongAndRadiusString(searchLocation,searchRadius)['latlngradiusString']
    paleobiodbURL = 'https://paleobiodb.org/data1.2/occs/list.json?rowcount&level=3%s%s&show=full' % (baseNameString,latlngradiusString)
    print (paleobiodbURL)
    warning = paleoSearch(paleobiodbURL)['warning']
    if (warning != None):
        flash(warning + ". Please try again.")
        return redirect(url_for('start_here'))
    else:
        ResultsFound = paleoSearch(paleobiodbURL)['ResultsFound']
        markers = paleoSearch(paleobiodbURL)['markers']
        allFossils = paleoSearch(paleobiodbURL)['allFossils']
        centerLat = getCenterMapMarker(searchLocation,searchRadius)['centerLat']
        centerLng = getCenterMapMarker(searchLocation,searchRadius)['centerLng']
        markers.append(getCenterMapMarker(searchLocation,searchRadius)['searchCenter'])
        zoomNumber = getZoomNumber(searchLocation, searchRadius)
        return render_template('map.html', centerLat=centerLat, centerLng=centerLng, searchTerm=searchTaxon, zoomNumber=zoomNumber, markers=markers, ResultsFound=ResultsFound, allFossils=allFossils)

def getSearchTaxon(taxonquery, taxonradio):
    if (taxonquery or taxonradio):
        if (taxonquery):  # Typing something in the search box overrides the radiobuttons
            searchTaxon = taxonquery
        else:
            searchTaxon = getTaxonRadioSearchString(taxonradio)
    else:
        searchTaxon = None
    return searchTaxon

def getTaxonRadioSearchString(taxonRadioResult):
    if taxonRadioResult == 'chordates':
        return "chordata"
    elif taxonRadioResult == 'dinosaursandfriends':
        return "saurischia,ornithischia,plesiosauria,ichthyosauria,pterosauria"
    elif taxonRadioResult == 'dinosaurs':
        return "saurischia,ornithischia"
    elif taxonRadioResult == 'sauropods':
        return "sauropoda"
    elif taxonRadioResult == 'theropods':
        return "Theropoda"
    elif taxonRadioResult == 'stegosaurs':
        return "Stegosauria"
    elif taxonRadioResult == 'ankylosaurs':
        return "ankylosauria"
    elif taxonRadioResult == 'hadrosaurs':
        return "hadrosauria"
    elif taxonRadioResult == 'ceratopsians':
        return "ceratopsia"
    elif taxonRadioResult == 'plesioichthyosauria':
        return "plesiosauria,ichthyosauria"
    elif taxonRadioResult == 'pterosauria':
        return "pterosauria"
    elif taxonRadioResult == 'birds':
        return "Aves"
    elif taxonRadioResult == 'mammals':
        return "mammalia"
    elif taxonRadioResult == 'hominids':
        return "Hominidae"
    elif taxonRadioResult == 'trilobites':
        return "Trilobita"
    else:
        return None

def getbaseNameString(searchTaxon):
    if (searchTaxon == None):
        return ""
    else:
        baseNameString = '&base_name=' + searchTaxon
        return baseNameString

def getLatLongAndRadiusString(searchLocation,searchRadius):
    if (searchLocation == ""):
        return {'latlngradiusString': "", 'centerLat': 0, 'centerLng': 0}
    else:
        # Geocoding an address into lat/long: https://developers.google.com/maps/documentation/javascript/geocoding (For Android, here: https://developer.android.com/training/building-location.html) A more user-friendly Python plugin is here https://pypi.python.org/pypi/geocoder
        g = geocoder.google(searchLocation)
        gLatJson = g.json['lat']
        gLngJson = g.json['lng']
        latmin = gLatJson - (searchRadius/2)
        latmax = gLatJson + (searchRadius/2)
        lngmin = gLngJson - (searchRadius/2)
        lngmax = gLngJson + (searchRadius/2)
        latlngradiusString = '&lngmin=%s&lngmax=%s&latmin=%s&latmax=%s' % (lngmin,lngmax,latmin,latmax)
        print (gLatJson)
        print (gLngJson)
        print (latlngradiusString)
        return {'latlngradiusString': latlngradiusString, 'centerLat': gLatJson, 'centerLng': gLngJson}


def getCenterMapMarker(searchLocation,searchRadius):
    if (searchLocation == ""):
        # Making centerpoint for taxonsearch map
        # firstFossil = fossilResults[0]
        firstFossil = SQLAFossil.query.first()
        firstFossilCoordinatePairs = firstFossil.coordinatePairs
        centerLat = firstFossilCoordinatePairs[0] # Map centers on the first result if no location chosen
        centerLng = firstFossilCoordinatePairs[1]
        searchCenter = None
    else:
        centerLat = getLatLongAndRadiusString(searchLocation,searchRadius)['centerLat']
        centerLng = getLatLongAndRadiusString(searchLocation,searchRadius)['centerLng']
        searchCenter = {'icon': '/static/images/mapicons/my_house.png', 'lat': centerLat, 'lng': centerLng, 'infobox': "Your chosen <b style='color:#00cc00;'> centerpoint </b>!" "<h2>HTML title</h2>" "<img src='/static/images/mapicons/tardis_by_pirate_elf.gif'>""<br><a href=https://en.wikipedia.org/wiki/Main_Page target='_blank'>Images and links allowed!</a>"}
    return {'searchCenter':searchCenter, 'centerLat':centerLat, 'centerLng':centerLng}

def getZoomNumber(searchLocation,searchRadius):
    if (searchLocation == ""):
        zoomNumber = 4
    elif (searchRadius >= 9):
        zoomNumber = 5
    elif (searchRadius >= 6):
        zoomNumber = 6
    elif (searchRadius >= 3):
        zoomNumber = 7
    elif (searchRadius == 2):
        zoomNumber=8
    else:
        zoomNumber=9
    return zoomNumber



@app.route('/cancel')
def cancel():
    flash('Search canceled. Returning to start.')
    clear_db()
    return redirect(url_for('start_here'))

if __name__ == '__main__':
    # db.create_all()
    app.run()
