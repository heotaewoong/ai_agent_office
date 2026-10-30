// Original Blender geometry replaces only the existing atrium's rigid shell.
export function createAtriumDetail({ world, space, quality, loadAsset }) {
  let phase=quality==='high'?'idle':'disabled',stage=null,container=null,active=false,disposed=false,generation=0,last=-Infinity;
  const show=value=>{
    active=value;
    for(const mesh of stage?.atriumArchitecture?.meshes||[])if(!mesh.isDisposed())mesh.setEnabled(!value);
    for(const mesh of container?.meshes||[])mesh.setEnabled(value);
  };
  const sync=()=>{
    if(disposed||phase==='disabled')return;
    const next=space.stages[0];
    if(next!==stage){
      show(false);container?.dispose();container=null;stage=next;generation++;phase='idle';
    }
    if(!stage?.atriumArchitecture||stage.node.isDisposed())return;
    const camera=world.scene.activeCamera?.globalPosition,origin=stage.node.getAbsolutePosition();
    const distance=camera?Math.hypot(camera.x-origin.x,camera.y-origin.y-3.5,camera.z-origin.z):Infinity;
    const near=space.layer==='office'&&distance<=(active?52:38);
    if(phase==='ready'){show(near);return;}
    if(!near||phase!=='idle')return;
    phase='loading';const ticket=generation,owner=stage;
    Promise.resolve().then(loadAsset).then(value=>{
      if(disposed||ticket!==generation||owner.node.isDisposed()){value.dispose();return;}
      container=value;
      const visible=value.meshes.filter(mesh=>mesh.getTotalVertices()>0);
      if(visible.length!==4||visible.reduce((n,mesh)=>n+mesh.getTotalIndices()/3,0)!==6204)throw Error('Unexpected atrium geometry');
      for(const mesh of value.meshes){
        mesh.setEnabled(false);mesh.isPickable=false;mesh.checkCollisions=false;
        if(!mesh.parent)mesh.parent=owner.node;
      }
      value.addAllToScene();
      for(const mesh of value.meshes){
        mesh.computeWorldMatrix(true);mesh.freezeWorldMatrix();
        if(mesh.getTotalVertices()){world.castShadow(mesh);world.receiveShadow(mesh);}
      }
      phase='ready';sync();
    }).catch(()=>{
      if(!disposed&&ticket===generation){phase='failed';container?.dispose();container=null;show(false);}
    });
  };
  const observer=phase==='disabled'?null:world.scene.onBeforeRenderObservable.add(()=>{
    const now=performance.now();if(now-last>=250){last=now;sync();}
  });
  const dispose=()=>{
    if(disposed)return;show(false);disposed=true;generation++;
    if(observer)world.scene.onBeforeRenderObservable.remove(observer);
    container?.dispose();container=null;
  };
  world.scene.onDisposeObservable.addOnce(dispose);
  return {sync,dispose,status:()=>({phase,active,disposed})};
}

export function installAtriumDetail(office,B,fetchAsset=fetch){
  if(!office?.world?.scene)return null;
  const {world,space,quality}=office;
  return createAtriumDetail({world,space,quality,loadAsset:async()=>{
    const response=await fetchAsset(new URL('assets/atrium-detail-v3.json',import.meta.url),{signal:AbortSignal.timeout(8000)});
    if(!response.ok)throw Error('Atrium asset unavailable');
    const text=await response.text();if(text.length>900000)throw Error('Atrium asset too large');
    return B.SceneLoader.LoadAssetContainerAsync('','data:'+text,world.scene,undefined,'.babylon');
  }});
}
if(typeof document!=='undefined'){
  const start=()=>{const office=window.__officeWorld;if(office?.world?.scene&&!office.world.atriumDetail)office.world.atriumDetail=installAtriumDetail(office,window.BABYLON);};
  if(document.readyState!=='complete')document.addEventListener('DOMContentLoaded',start,{once:true});
  start();
}
