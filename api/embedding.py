from schemas.entity import NodeVector as NV
import datetime as date

#Create
async def Create(node_id: str, user_id: str):
    result = NV()
    result.node_id = node_id
    
    result.created_at = date.datetime.now()
    result.created_by = user_id

    result.updated_at = date.datetime.now()
    result.updated_by = user_id

    print(result)
    return result

# #read
# async def Find():

# #read all
# async def FindAll():

# #update
# async def Update():

# #delete
# async def Delete():