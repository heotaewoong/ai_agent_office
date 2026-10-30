// A Blender-authored player appearance uses the existing movement and pose pivots.
export function createGuideAvatar({world,controls,space,quality,loadAsset}){
  let phase=quality==='high'?'idle':'disabled',container=null,disposed=false,last=-Infinity;
  const originals=new Map();
  const restore=()=>{for(const [mesh,visible] of originals)if(!mesh.isDisposed())mesh.isVisible=visible;originals.clear();};
  const sync=()=>{
    if(disposed||phase!=='idle'||space.view!=='walk')return;
    const avatar=controls.player?.av;if(!avatar||avatar.root.isDisposed())return;
    phase='loading';
    Promise.resolve().then(loadAsset).then(value=>{
      if(disposed||avatar.root.isDisposed()){value.dispose();return;}
      container=value;
      const meshes=value.meshes.filter(mesh=>mesh.getTotalVertices()>0),parts=new Set();
      for(const mesh of meshes){
        const part=mesh.metadata?.rigPart;
        if(!['root','armL','armR','legL','legR'].includes(part))throw Error('Unknown guide rig pivot');
        parts.add(part);
      }
      if(meshes.length!==14||parts.size!==5||meshes.reduce((n,mesh)=>n+mesh.getTotalIndices()/3,0)!==3672)throw Error('Unexpected guide geometry');
      for(const mesh of avatar.root.getChildMeshes())if(mesh!==avatar.marker)originals.set(mesh,mesh.isVisible);
      for(const mesh of meshes){
        mesh.parent=avatar[mesh.metadata.rigPart];mesh.setEnabled(true);mesh.isPickable=false;mesh.checkCollisions=false;
        world.castShadow(mesh);world.receiveShadow(mesh);
      }
      value.addAllToScene();
      for(const mesh of originals.keys())mesh.isVisible=false;
      phase='ready';
    }).catch(()=>{if(!disposed){container?.dispose();container=null;restore();phase='failed';}});
  };
  const observer=phase==='disabled'?null:world.scene.onBeforeRenderObservable.add(()=>{
    const now=performance.now();if(now-last>=250){last=now;sync();}
  });
  const dispose=()=>{
    if(disposed)return;disposed=true;restore();
    if(observer)world.scene.onBeforeRenderObservable.remove(observer);
    container?.dispose();container=null;
  };
  world.scene.onDisposeObservable.addOnce(dispose);
  return{sync,dispose,status:()=>({phase,disposed})};
}

export function installGuideAvatar(office,B,fetchAsset=fetch){
  if(!office?.world?.scene)return null;
  const {world,controls,space,quality}=office;
  return createGuideAvatar({world,controls,space,quality,loadAsset:async()=>{
    const response=await fetchAsset(new URL('assets/guide-avatar-v1.json',import.meta.url),{signal:AbortSignal.timeout(8000)});
    if(!response.ok)throw Error('Guide appearance unavailable');
    const text=await response.text();if(text.length>1500000)throw Error('Guide appearance too large');
    return B.SceneLoader.LoadAssetContainerAsync('','data:'+text,world.scene,undefined,'.babylon');
  }});
}
if(typeof document!=='undefined'){
  const start=()=>{const office=window.__officeWorld;if(office?.world?.scene&&!office.world.guideAvatar)office.world.guideAvatar=installGuideAvatar(office,window.BABYLON);};
  if(document.readyState!=='complete')document.addEventListener('DOMContentLoaded',start,{once:true});
  start();
}
