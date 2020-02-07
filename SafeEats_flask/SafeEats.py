#!/usr/bin/python
import joblib
from flask import Flask, render_template, flash, request, redirect, url_for
from SafeEats_flask import app
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
import pandas as pd
import psycopg2
import datetime, re, requests
from geopy.distance import geodesic
import json
from sklearn.preprocessing import MinMaxScaler


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
    cols = ['dba','zip','distance','yelp_name', 'url', 'review_count', 'rating', 'display_phone']
    top3_yelp = pd.DataFrame(columns = cols)
    yelp_dict = list()
    for restaurant, rest_zip, distance in zip(top3['dba'], top3['zipcode'], top3['distance']): 
        term = restaurant
        zipcode = rest_zip
        params = {'term': term, "location": zipcode}
        r=requests.get(url, params=params, headers=headers)
        if r.status_code == 429:
            break
        search_result = json.loads(r.text)
        if search_result['total']== 0:
            top3_yelp = top3_yelp.append(pd.Series([term, zipcode, distance, 'YELP ERROR!', 'YELP ERROR!',  'YELP ERROR!', 'YELP ERROR!', 'YELP ERROR!'], index=top3_yelp.columns), ignore_index= True)
        else:
            business = search_result['businesses'][0]
            yelp_dict.append(business)
            top3_yelp = top3_yelp.append(pd.Series([term, zipcode, distance, business['name'], business['url'],  business['review_count'], business['rating'], business['display_phone']], index=top3_yelp.columns), ignore_index= True)
    return top3_yelp

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
  if Street == '':
      return reload_after_error("Uh oh! You must enter an address")
  if zip_code == '':
      return reload_after_error("Uh oh! You must enter a zip code")
  if Dist =='':
      return reload_after_error("Uh oh! You must enter a distance")
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
  username = 'ubuntu'                    
  dbname = 'Health_Inspection'
  con=None
  con = psycopg2.connect(database = dbname, user = username, host='localhost')
  query = "SELECT latitude, longitude, dba,boro, last_insp_type, last_insp_num_flags,ny311_complaints,zipcode, cuisine_description,num_years_active, cuisine, avg_num_critical_flags_per_year, population,population_density, serious_housing_code_violations  FROM dataforapp WHERE cuisine_reduced= '%s' " %(cuisine) 
  query_results=pd.read_sql_query(query,con)
  query_results['distance'] = query_results.apply(lambda row: get_miles(row,location),axis=1)  
  data = query_results[query_results['distance']< Dist]
  data4model = data[['avg_num_critical_flags_per_year', 'ny311_complaints',
       'last_insp_type', 'last_insp_num_flags',
       'boro', 'num_years_active', 'cuisine', 
       'population', 'population_density','serious_housing_code_violations']]
  scaler = MinMaxScaler()
  scaler.fit(data4model)
  data4model = scaler.transform(data4model)
  model_from_pickle = joblib.load('final_model.pkl')
  results = model_from_pickle.predict(data4model)
  data['result'] = results.tolist()
  data = data[data['result']==1]
  data=data.sort_values('distance')
  if len(data) >= 3:
      top3 = data[['dba', 'zipcode', 'distance']][0:3]
  else:
      top3 = data[['dba', 'zipcode', 'distance']][0:len(data)]
  top3['zipcode'] = top3['zipcode'].astype(int)
  yelp_output = search_yelp(top3)
  yelp_output['distance'] = yelp_output['distance'].round(2)
  return render_template("output.html", cuisine = cuisine, Dist = Dist, address = Full_Address, yelp_output = yelp_output)


if __name__ == '__main__':
	app.run(host='0.0.0.0',debug=False)