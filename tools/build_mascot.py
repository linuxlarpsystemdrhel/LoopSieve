"""Generate original lightweight GLTF 2.0 character mesh, no third-party assets."""
import base64, json, math, struct
from pathlib import Path

U=28; V=18
pos=[]; norm=[]; indices=[]
for row in range(V+1):
    theta=math.pi*row/V
    for col in range(U+1):
        phi=2*math.pi*col/U
        x=math.sin(theta)*math.cos(phi)
        y=math.cos(theta)
        z=math.sin(theta)*math.sin(phi)
        pos.extend([x,y,z]);norm.extend([x,y,z])
for r in range(V):
    for c in range(U):
        a=r*(U+1)+c;b=a+U+1
        if r!=0:indices.extend([a,b,a+1])
        if r!=V-1:indices.extend([a+1,b,b+1])
blob=bytearray()
views=[]
def push(data,target):
    while len(blob)%4:blob.append(0)
    offset=len(blob);blob.extend(data)
    views.append({'buffer':0,'byteOffset':offset,'byteLength':len(data),'target':target})
    return len(views)-1
pi=push(struct.pack('<%sf'%len(pos),*pos),34962)
ni=push(struct.pack('<%sf'%len(norm),*norm),34962)
ii=push(struct.pack('<%sH'%len(indices),*indices),34963)
count=len(pos)//3
accessors=[{'bufferView':pi,'componentType':5126,'count':count,'type':'VEC3','min':[-1,-1,-1],'max':[1,1,1]},
           {'bufferView':ni,'componentType':5126,'count':count,'type':'VEC3'},
           {'bufferView':ii,'componentType':5123,'count':len(indices),'type':'SCALAR'}]
colors={'shell':[0.62,0.79,0.69,1], 'belly':[0.93,0.91,0.79,1], 'eye':[0.095,0.15,0.15,1],
        'pink':[0.87,0.57,0.53,1], 'detail':[0.28,0.42,0.38,1], 'shine':[1,1,0.95,1]}
materials=[{'name':k,'pbrMetallicRoughness':{'baseColorFactor':v,'metallicFactor':0,'roughnessFactor':0.83}} for k,v in colors.items()]
meshes=[{'name':k,'primitives':[{'attributes':{'POSITION':0,'NORMAL':1},'indices':2,'material':n,'mode':4}]} for n,k in enumerate(colors)]
nodes=[]
def n(name,material,trans,scale,rotation=None):
    o={'name':name,'mesh':list(colors).index(material),'translation':trans,'scale':scale}
    if rotation:o['rotation']=rotation
    nodes.append(o)
# Front points toward +Z. Character is a soft pear-shaped forest sprite.
n('body','shell',[0,0,0],[0.83,0.91,0.66])
n('belly','belly',[0,-0.19,0.546],[0.52,0.53,0.24])
n('left_bloom','shell',[-0.54,0.76,0.03],[0.30,0.46,0.22],[0,0,-0.20,0.98])
n('right_bloom','shell',[0.54,0.76,0.03],[0.30,0.46,0.22],[0,0,0.20,0.98])
n('head_tip','shell',[0,0.89,-0.08],[0.32,0.27,0.22])
n('left_arm','shell',[-0.76,-0.22,0],[0.22,0.37,0.27],[0,0,0.3,0.95])
n('right_arm','shell',[0.76,-0.22,0],[0.22,0.37,0.27],[0,0,-0.3,0.95])
n('left_foot','detail',[-0.38,-0.76,0.14],[0.34,0.19,0.38])
n('right_foot','detail',[0.38,-0.76,0.14],[0.34,0.19,0.38])
n('left_eye','eye',[-0.29,0.23,0.572],[0.098,0.155,0.067])
n('right_eye','eye',[0.29,0.23,0.572],[0.098,0.155,0.067])
n('left_glint','shine',[-0.32,0.286,0.628],[0.028,0.043,0.025])
n('right_glint','shine',[0.26,0.286,0.628],[0.028,0.043,0.025])
n('left_cheek','pink',[-0.48,-0.02,0.51],[0.16,0.07,0.03])
n('right_cheek','pink',[0.48,-0.02,0.51],[0.16,0.07,0.03])
n('nose','detail',[0,-0.03,0.661],[0.04,0.035,0.035])
n('smile','detail',[0,-0.15,0.64],[0.12,0.019,0.033])
asset={'asset':{'version':'2.0','generator':'LoopSieve original procedural mascot generator'},
       'scene':0,'scenes':[{'name':'Pip scene','nodes':list(range(len(nodes)))}],
       'nodes':nodes,'meshes':meshes,'materials':materials,
       'buffers':[{'byteLength':len(blob),'uri':'data:application/octet-stream;base64,'+base64.b64encode(blob).decode()}],
       'bufferViews':views,'accessors':accessors}
path=Path(__file__).resolve().parents[1]/'src'/'loopsieve'/'assets'/'pip.gltf'
path.write_text(json.dumps(asset,separators=(',',':')))
print(path, len(nodes),'nodes',len(indices)//3,'triangles',len(blob),'binary bytes')
