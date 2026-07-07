
import pandas as pd




df = pd.read_csv('C:/Users/73823/Desktop/DBM/project/data/gdelt_2024_na_000000000001.csv', sep='\t', nrows=5, header=None)

df.to_csv("sample.csv")