import os
import uvicorn
if __name__=='__main__':uvicorn.run('eco_planner.api:app',host='0.0.0.0',port=int(os.environ.get('PORT','10000')),workers=1)
