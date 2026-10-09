// Retain only outstanding submissions, scoped by account and operation.
function read(scope:string):Array<{signature:string,key:string}>{
  try{const stored=JSON.parse(localStorage.getItem('luma-pending-'+scope)||'[]');return Array.isArray(stored)?stored:stored?.key?[stored]:[]}catch{return []}
}
export function pendingKey(scope:string,payload:unknown){
  const name='luma-pending-'+scope,signature=JSON.stringify(payload),entries=read(scope)
  const old=entries.find(x=>x.signature===signature)
  if(old)return old.key
  const key=crypto.randomUUID();entries.push({signature,key});localStorage.setItem(name,JSON.stringify(entries));return key
}
export function completePending(scope:string,payload:unknown){
  const entries=read(scope).filter(x=>x.signature!==JSON.stringify(payload)),name='luma-pending-'+scope
  if(entries.length)localStorage.setItem(name,JSON.stringify(entries));else localStorage.removeItem(name)
}
