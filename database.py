import mysql.connector

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Prabir@321",
    database="pulse_medicare"
)

cursor = db.cursor()
