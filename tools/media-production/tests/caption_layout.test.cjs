const {test}=require('node:test');
const assert=require('node:assert/strict');
const {captionBoundsFromOffsets}=require('../caption_layout.cjs');
test('uses local layout offsets rather than transient global client coordinates',()=>{
 const element={offsetLeft:85,offsetTop:155,offsetWidth:840,offsetHeight:202,
   getBoundingClientRect(){throw Error('offscreen viewport coordinates must not be used');}};
 assert.deepEqual(captionBoundsFromOffsets(element,0),{left:85,right:925,top:155,bottom:357,height:202});
});
