#!/usr/bin/python
import joblib
from flask import render_template
from flask import request 
from SafeEats_flask import app
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
import pandas as pd
import psycopg2
import datetime, re, requests
from geopy.distance import geodesic
import json

#app = Flask(__name__)





def geocode_location(location):
    query = re.sub(r'\s+', '\+', location)
    request = f'https://nominatim.openstreetmap.org/search?q={query}&format=json'
    res = requests.get(request)
    if res.status_code == 200:
        lat = float(res.json()[0]['lat'])
        lon = float(res.json()[0]['lon'])
        return (lat, lon)
    else:
        return (None, None)

def calc_today():
    now = datetime.datetime.now()
    now = datetime.datetime(now.year, now.month, now.day)
    now = now.strftime("%Y-%m-%d")
    return now

def reload_after_error(error):
    now = calc_today()
    return render_template('input.html', now=now, error=error)

def get_miles(row, location):
    loc1 = (row['latitude'], row['longitude'])
    return geodesic(loc1, location).miles

def search_yelp(top3):
    with open('yelp_credentials.json') as creds:    
        credentials = json.load(creds)
    api_key = credentials['api_key']
    headers = {'Authorization': 'Bearer %s' % api_key}
    url = 'https://api.yelp.com/v3/businesses/search'
    rest_list = top3
    responses = list()
    for restaurant, rest_zip in zip(rest_list['dba'], rest_list['zipcode']): 
        term = restaurant
        zipcode = rest_zip
        params = {'term': restaurant, "location": zipcode}
        r=requests.get(url, params=params, headers=headers)
        if r.status_code == 429:
            break
        data = json.loads(r.text)
        responses.append(data)
        return responses

@app.route('/', methods = ['GET', 'POST'])
def rest_input():
    today = calc_today()
    return render_template("input.html", today=today)


@app.route('/output', methods = ['GET', 'POST'])
def rest_output():
  #pull 'rest_name'  and 'zip_code' from input fields and store it
  cuisine = request.form.get('cuisine')
  Street = request.form.get('inputAddress')
  zip_code = request.form.get('inputZip')
  Dist = int(request.form.get('inputDist')) 
  Full_Address = Street + ', New York City, New York ' + zip_code
  if zip_code.startswith('1') == False:
      return reload_after_error("Uh oh! Looks like that location isn't in New York City. Please try again.")
  location = geocode_location(Full_Address)
  if location[0] is None:
      return reload_after_error("Uh oh! We can't find that location on the map. Please try again.")
  if (location[0] < 40.5) | (location[0] > 41):
      return reload_after_error("Uh oh! Looks like that location isn't in New York City. Please try again.")
  if (location[1] < (-74.5)) | (location[1] > (-73)):
      return reload_after_error("Uh oh! Looks like that location isn't in New York City. Please try again.")
    #just select predictor data from the SQL database for the restaurant they entered
  username = 'rabarry'                    
  dbname = 'Health_Inspection'
  db = create_engine('postgres://%s@localhost/%s'%(username,dbname))
  con = psycopg2.connect(database = dbname, user = username)
  query = "SELECT latitude, longitude, dba,boro, last_insp_type, last_insp_num_flags,ny311_complaints,zipcode, cuisine_description,num_years_active, cuisine, income_diversity_ratio,median_income, population,population_density, poverty_rate,public_housing, racial_diversity_index,serious_crime_rate,serious_housing_code_violations, NOW() - last_insp_date AS insp_date_diff  FROM dataforapp WHERE cuisine_reduced= '%s' " %(cuisine) 
  query_results=pd.read_sql_query(query,con)
  query_results['distance'] = query_results.apply(lambda row: get_miles(row,location),axis=1)  
  data = query_results[query_results['distance']< Dist]
  data['insp_date_diff2'] = (data['insp_date_diff'].astype(str)).apply(lambda x: x.split('d')[0])
  data4model = data[['insp_date_diff2', 'ny311_complaints',
       'last_insp_type', 'last_insp_num_flags',
       'boro', 'num_years_active', 'cuisine', 'income_diversity_ratio', 'median_income',
       'population', 'population_density',
       'poverty_rate', 'public_housing',
       'racial_diversity_index', 'serious_crime_rate',
       'serious_housing_code_violations']]
  knn_from_pickle = joblib.load('knn_model.pkl')
  results = knn_from_pickle.predict(data4model)
  data['result'] = results.tolist()
  data = data[data['result']==1]
  data=data.sort_values('distance')
  if len(data) >= 3:
      top3 = data[['dba', 'zipcode']][0:3]
  else:
      top3 = data[['dba', 'zipcode']][0:len(data)]
  #yelp_links = search_yelp(top3)
  return render_template("output.html", cuisine = cuisine, Dist = Dist, address = Full_Address, top3=top3)


if __name__ == '__main__':
	app.run(host='0.0.0.0',debug=False)