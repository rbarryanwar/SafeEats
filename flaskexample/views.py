from sklearn.externals import joblib
from flask import render_template
from flask import request 
from flaskexample import app
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
import pandas as pd
import psycopg2

username = 'postgres' #add your username here (same as previous postgreSQL)                      
#host = 'localhost'
dbname = 'Health_Inspection'
db = create_engine('postgres://%s@localhost/%s'%(username,dbname))
con = None
con = psycopg2.connect(database = dbname, user = username)


@app.route('/', methods = ['GET', 'POST'])
def rest_input():
    rest_name = str(request.form)
    return render_template("input.html")

@app.route('/output', methods = ['GET', 'POST'])
def rest_output():
  #pull 'rest_name'  and 'zip_code' from input fields and store it
  rest_name = request.args.get('rest_name')
  zip_code = int(request.args.get('zip'))
    #just select predictor data from the SQL database for the restaurant they entered
  query = "SELECT \"BORO_cat\",\"CUISINE DESCRIPTION_cat\",\"Second_Last_Insp_Num_CriticialFlags\",\"Second_Last_Insp_Type_cat\",\"Insp_Date_Diff\", \"num_years_active\"  FROM \"DataforWk2\" WHERE \"DBA\"='%s' AND \"ZIPCODE\"=%d" %(rest_name, zip_code)
  print(query)
  query_results=pd.read_sql_query(query,con)
  print(query_results)
  logistic_from_pickle = joblib.load('baseline_model.pkl')
  the_result = logistic_from_pickle.predict(query_results)
  if the_result==[1]:
      the_result_YN = 'safe!'
  elif the_result ==[0]:
      the_rsult_YN = 'unsafe! try somewhere else!'
  return render_template("output.html", the_result = the_result_YN)
