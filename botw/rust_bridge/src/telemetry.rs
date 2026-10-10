//! Guest Link telemetry sourced only from THIS Ryujinx session.
//! Replaces legacy Python relay, whose startup replayed prior-session positions
//! from the append-only combined botwcraft.log.
use std::{fs,path::PathBuf,thread,time::Duration,
  sync::{Arc,Mutex}};
use serde_json::json;
use crate::engine::Engine;
fn log_path()->PathBuf{
 std::env::var_os("BOTWCRAFT_LOG").map(PathBuf::from)
    .unwrap_or_else(||PathBuf::from("logs/botwcraft.log"))
}
fn position(line:&str)->Option<[f64;3]>{
 if !line.starts_with("[RYUJINX_PROCESS] "){return None}
 let rest=line.split_once("BotwCraft:NATIVE_POSITION_MILLI")?.1;
 let mut numbers=[None;3];
 for token in rest.split_whitespace(){
  for (i,prefix) in ["x=","y=","z="].iter().enumerate(){
   if let Some(value)=token.strip_prefix(prefix){
    numbers[i]=value.parse::<i64>().ok()
   }
  }
 }
 let [Some(x),Some(y),Some(z)]=numbers else {return None};
 if x==0 && y==0 && z==0 {return None}
 let v=[x as f64/1000.0,y as f64/1000.0,z as f64/1000.0];
 if v.iter().all(|a|a.is_finite() && a.abs()<100000.0) {Some(v)}else{None}
}
pub fn run(state:Arc<Mutex<Engine>>){
 let path=log_path();
 // Set start at EOF: the bridge is spawned before Ryujinx.
 // NO historical Link pose from a previous run can enter the new session.
 let mut at=fs::metadata(&path).map(|m|m.len() as usize).unwrap_or(0);
 let mut partial=String::new();
 let mut seen_start=false;
 let mut last_pos:Option<[f64;3]>=None;
 loop{
  if let Ok(data)=fs::read(&path){
   if data.len()<at{
    at=data.len();partial.clear();seen_start=false;last_pos=None;
   }
   if data.len()>at{
    let chunk=String::from_utf8_lossy(&data[at..]);
    at=data.len();
    partial.push_str(&chunk);
    let mut consumed=0;
    while let Some(i)=partial[consumed..].find('\n'){
      let end=consumed+i;
      let line=partial[consumed..end].trim_end_matches('\r');
      consumed=end+1;
      if line.starts_with("[LAUNCH] RYUJINX_PROCESS:"){
       seen_start=true;last_pos=None;
       println!("[RUST_RELAY] New Ryujinx session detected; old telemetry discarded");
      }else if line.contains("[LAUNCH] RYUJINX_PROCESS exited"){
       seen_start=false;last_pos=None;
      }else if seen_start{
       if let Some(pos)=position(line){
        if last_pos!=Some(pos){
         if let Ok(mut e)=state.lock(){
          let res=e.command(json!({"type":"pose",
              "x":pos[0],"y":pos[1],"z":pos[2],
              "yaw":0.0,"pitch":0.0,"world":1}));
          if res.get("ok").and_then(|v|v.as_bool()).unwrap_or(false){
           last_pos=Some(pos);
           println!("[RUST_RELAY] Live Link pose: {:.3} {:.3} {:.3}",pos[0],pos[1],pos[2]);
          }
         }
        }else{
         // Repeated position is normal while Link stands still. Keep the
         // heartbeat alive as long as Ryujinx itself is still measuring Link.
         if let Ok(mut e)=state.lock(){
          e.command(json!({"type":"pose","x":pos[0],"y":pos[1],"z":pos[2],
            "yaw":0.0,"pitch":0.0,"world":1}));
         }
        }
       }
      }
    }
    if consumed>0{partial.drain(..consumed);}
    if partial.len()>8192{partial.clear();}
   }
  }
  thread::sleep(Duration::from_millis(100));
 }
}
#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn parse_only_real_guest_output(){
  assert_eq!(position("[RYUJINX_PROCESS] 00:01 |W| BotwCraft:NATIVE_POSITION_MILLI x=-1126979 y=237395 z=1910071"),
    Some([-1126.979,237.395,1910.071]));
  assert_eq!(position("[RYUJINX_RELAY] sent: -1126.979, 237.395, 1910.071"),None);
  assert_eq!(position("[RYUJINX_PROCESS] BotwCraft:NATIVE_POSITION_MILLI x=0 y=0 z=0"),None);
 }
}
