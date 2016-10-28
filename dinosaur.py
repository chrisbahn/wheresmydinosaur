from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import os
import json, requests, sys, random
from sqlite3 import dbapi2 as sqlite3
from wtforms import RadioField, SubmitField,IntegerField,TextAreaField,SelectField
from flask_wtf import Form
import urllib.request
from flask_googlemaps import GoogleMaps # https://pypi.python.org/pypi/Flask-GoogleMaps/
from flask_googlemaps import Map, icons
import geocoder # https://pypi.python.org/pypi/geocoder
import pycountry # https://pypi.python.org/pypi/pycountry
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

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


class Fossil(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	fossilName = db.Column(db.String(80))
	taxonomy = db.Column(db.PickleType)
	location = db.Column(db.String(100))
	age = db.Column(db.String(50))
	coordinatePairs = db.Column(db.PickleType)
	paleoenv = db.Column(db.String(30))
	geocomments = db.Column(db.String(200))
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

class GeoTime(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	interval_no = db.Column(db.Integer)
	scale_level = db.Column(db.Integer)
	interval_name = db.Column(db.String(30))
	color = db.Column(db.String(7))
	max_ma = db.Column(db.Float)
	min_ma = db.Column(db.Float)
	parent_no = db.Column(db.Integer)

	def __init__(self, interval_no, scale_level, interval_name, color, max_ma, min_ma, parent_no):
		self.interval_no = interval_no
		self.scale_level = scale_level
		self.interval_name = interval_name
		self.color = color
		self.max_ma = max_ma
		self.min_ma = min_ma
		self.parent_no = parent_no


def create_GeoTime_objects():
	paleobiodbResponse = urllib.request.urlopen('https://paleobiodb.org/data1.2/intervals/list.json?scale=1')
	paleobiodbResponseJSONString = paleobiodbResponse.read().decode('UTF-8')
	paleobiodbResponseJson = json.loads(paleobiodbResponseJSONString)
	paleobiodbRecordsJson = paleobiodbResponseJson['records']
	for line in paleobiodbRecordsJson:
		interval_no = int(str(line['oid']).strip('int:'))
		scale_level = int(line['lvl'])
		if ('nam' in line):
			interval_name = str(line['nam'])
		elif ('oei' in line):
			interval_name = str(line['oei'])
		color = str(line['col'])
		max_ma = float(line['eag'])
		min_ma = float(line['lag'])
		if ('pid' in line):
			parent_no = int(str(line['pid']).strip('int:'))
		newGeoTime = GeoTime(interval_no, scale_level, interval_name, color, max_ma, min_ma, parent_no)
		db.session.add(newGeoTime)
		db.session.commit()
		print(interval_name + " " + str(interval_no) + " " + str(parent_no))



def clear_db():
	allFossils = Fossil.query.all()
	for fossilInstance in allFossils:
		db.session.delete(fossilInstance)
		db.session.commit()



@app.route('/')
def start_here():
	taxonRadioButtonList = getTaxonRadioButtonList()
	allGeoTimes = GeoTime.query.order_by(GeoTime.min_ma,GeoTime.scale_level).all()
	return render_template('home.html', searchresults=None, taxonRadioButtonList=taxonRadioButtonList,allGeoTimes=allGeoTimes,getTimeScaleDivisionName=getTimeScaleDivisionName,round=round)

def getTaxonRadioButtonList():
	#('id', 'value', 'displayname', 'indent','searchterm')
	taxonRadioButtonList = [
		('chkDinosAndFriends', 'dinosaursandfriends', 'Dinosaurs and their close relatives',0,'saurischia,ornithischia,plesiosauria,ichthyosauria,pterosauria'),
		('chkDinos', 'dinosaurs', 'All dinosaurs',1,'saurischia,ornithischia'),
		('chkSauropods', 'sauropods', 'Sauropods (Brachiosaurus, etc.)',2,'sauropoda'),
		('chkTheropods', 'theropods', 'Theropods (Tyrannosaurus, etc.)',2,'theropoda'),
		('chkStegosaurs', 'stegosaurs', 'Stegosaurs',2,'stegosauria'),
		('chkAnkylosaurs', 'ankylosaurs', 'Ankylosaurs',2,'ankylosauria'),
		('chkOrnithopods', 'ornithopods', 'Ornithopods (duckbills and iguanodonts)',2,'ornithopoda'),
		('chkCeratopsians', 'ceratopsians', 'Ceratopsians (Triceratops, etc.)',2,'ceratopsia'),
		('chkPlesioichthyosauria', 'plesioichthyosauria', 'Plesiosaurs and ichthyosaurs',1,'plesiosauria,ichthyosauria'),
		('chkPterosauria', 'pterosauria', 'Pterosaurs',1,'pterosauria'),
		('chkBirds', 'birds', 'Birds',0,'aves'),
		('chkMammals', 'mammals', 'Mammals',0,'mammalia'),
		('chkHominids', 'hominids', 'Hominids (ancient humans and their relatives)',1,'hominidae'),
		('chkTrilobites', 'trilobites', 'Trilobites',0,'trilobita'),
		('chkChordates', 'chordates', 'All chordates (animals with backbones)',0,'chordata'),
		]
	return taxonRadioButtonList


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
		for taxonResult in paleobiodbRecordsJson:
			filterPaleobiodbResponseJson(taxonResult)
	allFossils = Fossil.query.all()
	markers = get_markers(allFossils)
	return {'ResultsFound': ResultsFound, 'markers': markers, 'allFossils': allFossils, 'warning': warning}

def filterPaleobiodbResponseJson(taxonResult):
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
	create_fossil_objects(lat, lng, taxonName, trank_phylum, trank_class, trank_order, trank_family, trank_genus, nation, state, county, geologicAge, paleoenv, max_ma, min_ma, geocomments)  # Creates a Fossil object

def create_fossil_objects(lat,lng,taxonName,trank_phylum,trank_class,trank_order,trank_family,trank_genus,nation,state,county,geologicAge,paleoenv,max_ma,min_ma,geocomments):
	# This takes the raw JSON variables from paleobiodbRecordsJson, created in paleoSearch(), and creates a set of Fossil objects for mapping, etc.
	coordinatePairs = [lat, lng]  # lat/long
	fossilName = getfossilName(taxonName, trank_phylum, trank_class, trank_order, trank_family,trank_genus)  # This is the fossil's display name
	taxonomy = getTaxonomy(trank_phylum, trank_class, trank_order, trank_family,trank_genus)  # This is the fossil's tree-of-life designations
	location = getLocation(nation, state, county, geocomments)
	age = getGeologicAge(geologicAge, max_ma, min_ma)
	newFossil = Fossil(fossilName, taxonomy, location, age, coordinatePairs, paleoenv, geocomments)
	db.session.add(newFossil)
	db.session.commit()



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
		elif (nation == 'United States') or (nation == 'US'):
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
		fossilName = "Species not recorded"
	return fossilName

def getTaxonomy(trank_phylum, trank_class, trank_order, trank_family, trank_genus):
	taxonomy = {'phylum': trank_phylum, 'class': trank_class, 'order': trank_order, 'family': trank_family, 'genus': trank_genus}
	return taxonomy

def getGeologicAge(geologicAge,max_ma,min_ma):
	eras = GeoTime.query.filter_by(scale_level=2)
	periods = GeoTime.query.filter_by(scale_level=3)
	age = ""
	firstpart = ""
	years = ""
	if (geologicAge == None):
		age = "Geologic age unknown"
	else:
		for period in periods:
			for era in eras:
				if (era.interval_no == period.parent_no):
					if ((min_ma != None) and (period.max_ma >= ((max_ma + min_ma) / 2) >= period.min_ma)) or ((min_ma == None) and (period.max_ma >= max_ma >= period.min_ma)):
						firstpart = period.interval_name + " " + getTimeScaleDivisionName(period) + ", " + era.interval_name + " " + getTimeScaleDivisionName(era)
			if (max_ma < 1):
				if (min_ma != None):
					years = " (approx. " + str(round(((max_ma+min_ma)/2)*1000,2)) + " thousand years ago)"
				elif (min_ma == None):
					years = " (approx. " + str(max_ma*1000) + " thousand years ago)"
			elif (max_ma >= 1):
				if (min_ma != None):
					years = " (approx. " + str(round((max_ma+min_ma)/2,2)) + " million years ago)"
				elif (min_ma == None):
					years = " (approx. " + str(max_ma) + " million years ago)"
				else:
					years = ""
			age = firstpart + years
	return age

def getTimeScaleDivisionName(GeoTime):
	TimeScaleDivisionDict = {1: "eon", 2: "era", 3: "period", 4: "epoch", 5: "age"}
	TimeScaleDivisionName = TimeScaleDivisionDict[GeoTime.scale_level]
	return TimeScaleDivisionName

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
		print("coordinatePairs: " + str(coordinatePairs[0]) + ", " + str(coordinatePairs[1]))
		print("PHYLUM: " + str(taxonomy['phylum']) + ", CLASS: " + str(taxonomy['class']) + ", ORDER: " + str(taxonomy['order']) + ", FAMILY: " + str(taxonomy['family']) + ", GENUS: " + str(taxonomy['genus']))
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
	print('searchTaxon =' + str(searchTaxon))
	baseNameString = getbaseNameString(searchTaxon)
	searchLocation = request.args.get('locationquery')
	searchRadius = int(request.args.get('degrees'))
	print('searchLocation =' + str(searchLocation))
	latlngradiusString = getLatLongAndRadiusString(searchLocation,searchRadius)['latlngradiusString']
	searchGeoTime = str(request.args.get('geotimeradio'))
	print('searchGeoTime =' + str(searchGeoTime))
	searchGeoTimeString = getsearchGeoTimeString(searchGeoTime)

	paleobiodbURL = 'https://paleobiodb.org/data1.2/occs/list.json?rowcount&level=3%s%s%s&show=full' % (baseNameString,latlngradiusString,searchGeoTimeString)
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
	taxonRadioButtonList = getTaxonRadioButtonList()
	for item in taxonRadioButtonList:
		if taxonRadioResult == item[1]:
			return item[4]

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
		firstFossil = Fossil.query.first()
		firstFossilCoordinatePairs = firstFossil.coordinatePairs
		centerLat = firstFossilCoordinatePairs[0] # Map centers on the first result if no location chosen
		centerLng = firstFossilCoordinatePairs[1]
		searchCenter = None
	else:
		centerLat = getLatLongAndRadiusString(searchLocation,searchRadius)['centerLat']
		centerLng = getLatLongAndRadiusString(searchLocation,searchRadius)['centerLng']
		searchCenter = {'icon': '/static/images/mapicons/my_house.png', 'lat': centerLat, 'lng': centerLng, 'infobox': "Your chosen <b style='color:#00cc00;'> centerpoint </b>!" "<h2>You live here</h2>" "<img src='/static/images/mapicons/my_house.png'>""<br><a href=https://en.wikipedia.org/wiki/Main_Page target='_blank'>Images and links allowed!</a>"}
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

def getsearchGeoTimeString(searchGeoTime):
	if (searchGeoTime == None):
		searchGeoTimeString = ''
	elif (searchGeoTime == 'allpasteras'):
		searchGeoTimeString = ''
	elif (searchGeoTime == 'precambrian'):
		searchGeoTimeString = '&min_ma=541'
	else:
		searchGeoTimeString = '&interval=' + searchGeoTime
	return searchGeoTimeString




@app.route('/cancel')
def cancel():
	flash('Search canceled. Returning to start.')
	clear_db()
	return redirect(url_for('start_here'))

if __name__ == '__main__':
	db.create_all()
	allGeoTimes = GeoTime.query.all()
	for line in allGeoTimes:
		db.session.delete(line)
		db.session.commit()
	create_GeoTime_objects()
	app.run()
