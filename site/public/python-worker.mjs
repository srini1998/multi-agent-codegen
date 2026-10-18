import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';
let output='';
const py=await loadPyodide({stdout:s=>{output=(output+s+'\n').slice(-8000)},stderr:s=>{output=(output+s+'\n').slice(-8000)}});
postMessage({type:'ready'});
onmessage=async({data:{code,test,entry}})=>{try{
 const script=`import json\ncandidate_ns = {}\nexec(${JSON.stringify(code)}, candidate_ns)\nchecker_ns = {}\nexec(${JSON.stringify(test)}, checker_ns)\nchecker_ns['check'](candidate_ns[${JSON.stringify(entry)}])\n`;
 py.runPython(script);postMessage({type:'result',ok:true,output});
}catch(e){postMessage({type:'result',ok:false,output:output+'\n'+String(e).slice(-5000)})}};
