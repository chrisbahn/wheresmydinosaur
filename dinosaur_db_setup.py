import sqlite3, requests, json

def main():

#    if not hasattr(g, 'sqlite_db'):
    db = sqlite3.connect('paleozoic.db')  # This is the working db as of 9/29
#    rv.row_factory = sqlite3.Row

    db.execute('drop table if exists fossils')
    db.execute('create table fossils(line_id integer primary key, lat float, long float, taxonName text, trank_phylum text, trank_class text, trank_order text, trank_family text, trank_genus text, nation text, state text, county text, geologicAge text, paleoenv text, max_ma float, min_ma float, geocomments text)')

main()

# env text, phl text, cll text, odl text, fml text, ggc text