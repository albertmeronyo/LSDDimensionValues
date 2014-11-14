from bottle import route, run, template, request, static_file, abort
from pymongo import Connection
from SPARQLWrapper import SPARQLWrapper, JSON, SPARQLExceptions
from bson.son import SON
import urllib
import logging
import glob
import sys
import traceback
import os
import json
from pymongo import Connection
from bson.son import SON

__VERSION = 0.1

connection = Connection('localhost', 27017)
db = connection.lsddimensionsprod

@route('/version')
def version():
    return "Version " + str(__VERSION)

@route('/')
@route('/dimensions')
def lsd_dimensions():
    dims = db.dimensions.aggregate([
        {"$unwind" : "$dimensions"},
        {"$group": {"_id": {"uri": "$dimensions.uri", "label": "$dimensions.label"}, 
                    "dimensionsCount" : {"$sum" : 1}}},
        {"$sort": SON([("dimensionsCount", -1)])}
    ])
    # Local results json serialization -- dont do this at every request!
    local_json = []
    dimension_id = 0
    for result in dims["result"]:
        local_json.append({"id" : dimension_id,
                           "view" : "<a href='/dimensions/%s'><img src='/img/eye.png' alt='Details'></a>" % dimension_id,
                           "uri" : result["_id"]["uri"],
                           "label" : result["_id"]["label"],
                           "refs" : result["dimensionsCount"]
                           })
        dimension_id += 1
    with open('data.json', 'w') as outfile:
        json.dump(local_json, outfile)
    num_endpoints = db.dimensions.count()

    return template('lsd-dimensions', results=dims, num_endpoints=num_endpoints)

@route('/dimensions/:id', method='GET')
def get_dimension(id):
    # TODO: avoid this lazy load on demand
    local_json = None
    with open('data.json', 'r') as infile:
        local_json = json.load(infile)
    for dim in local_json:
        if int(dim['id']) == int(id):
            dimension_uri = dim['uri']
    # Search for all we got about dimension_uri
    endpoints_results = db.dimensions.find(
        {"dimensions.uri" : dimension_uri},
        {"endpoint.url" : 1}
    ).distinct("endpoint.url")
    codes_results = db.dimensions.aggregate([
        {"$unwind" : "$dimensions"}, 
        {"$unwind" : "$dimensions.codes"}, 
        {"$match" : {"dimensions.uri" : dimension_uri}}, 
        {"$group" : {"_id" : {"uri" : "$dimensions.codes.uri", "label" : "$dimensions.codes.label"}}}
    ])

    return template('dimension', dim=dimension_uri, endpoints=endpoints_results, codes=codes_results)

@route('/about', method='GET')
def about():
    return template('about')

@route('/dsds', method='GET')
def dsds():
    num_endpoints = db.dimensions.count()
    dsds = db.dsds.find(
        {},
        {"_id" : 0, "dsd.uri" : 1}
        )
    # Local results json serialization -- dont do this at every request!
    local_json = []
    dsd_id = 0
    for result in dsds:
        local_json.append({"id" : dsd_id,
                           "uri" : result["dsd"]["uri"]
                           })
        result["dsd"]["id"] = dsd_id
        dsd_id += 1
    with open('dsd_data.json', 'w') as outfile:
        json.dump(local_json, outfile)

    num_dsds = db.dsds.count()
    dsds.rewind()

    return template('dsds', num_endpoints=num_endpoints, results=dsds, num_dsds=num_dsds)

@route('/dsds/:id', method='GET')
def get_dsd(id):
    # TODO: avoid this lazy load on demand
    local_json = None
    with open('dsd_data.json', 'r') as infile:
        local_json = json.load(infile)
    for dsd in local_json:
        if int(dsd['id']) == int(id):
            dsd_uri = dsd['uri']
    # Search for all we got about dsd_uri
    dsd_results = db.dsds.find(
        {"dsd.uri" : dsd_uri}
        )

    return template('dsd', dsd_uri=dsd_uri, dsd_results=dsd_results)

@route('/analytics', method='GET')
def analytics():
    # TODO: avoid this lazy load on demand

    ### 1. Dim-freq distribution
    dims = db.dimensions.aggregate([
        {"$unwind" : "$dimensions"},
        {"$group": {"_id": {"uri": "$dimensions.uri", "label": "$dimensions.label"}, 
                    "dimensionsCount" : {"$sum" : 1}}},
        {"$sort": SON([("dimensionsCount", -1)])}
    ])

    freqs = [dim["dimensionsCount"] for dim in dims["result"]]
    dim_names = [dim["_id"]["label"] for dim in dims["result"]]

    dims_freqs = [[dim_names[i], freqs[i]] for i in range(len(dim_names))]

    ### 2. Endpoints using LSD dimensions

    num_endpoints = db.dimensions.find({"endpoint" : {"$exists" : "1"}}).count()
    with_dims = db.dimensions.find({"dimensions" : {"$exists" : "1"}}).count()
    fracs = [['With dimensions', with_dims], ['Without dimensions', num_endpoints - with_dims]]

    ### 3. Dimensions with and without codes
    total_dims = len(dims["result"])
    codes = db.dimensions.aggregate([
        {"$match" : {"dimensions.codes.uri" : {"$exists" : 1}}}, 
        {"$unwind" : "$dimensions"}, 
        {"$unwind" : "$dimensions.codes"}, 
        {"$group": {"_id" : {"duri" : "$dimensions.uri"}}}
    ])
    with_codes = len(codes["result"])
    fracs_codes = [['With codes', with_codes], ['Without codes', total_dims - with_codes]]
    
    return template('analytics', dims=range(len(dim_names)), freqs=freqs, dims_freqs=dims_freqs, fracs=fracs, fracs_codes=fracs_codes)

# Static Routes
@route('/data.json')
def data():
    return static_file('data.json', root='./')

@route('/dsd_data.json')
def data():
    return static_file('dsd_data.json', root='./')

@route('/js/<filename:re:.*\.js>')
def javascripts(filename):
    return static_file(filename, root='views/js')

@route('/css/<filename:re:.*\.css>')
def stylesheets(filename):
    return static_file(filename, root='views/css')

@route('/img/<filename:re:.*\.(jpg|png|gif|ico)>')
def images(filename):
    return static_file(filename, root='views/img')

@route('/fonts/<filename:re:.*\.(eot|ttf|woff|svg)>')
def fonts(filename):
    return static_file(filename, root='views/fonts')

run(host = sys.argv[1], port = sys.argv[2], debug = True, reloader = True, server = 'cherrypy')
