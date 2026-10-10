#[cfg(target_os="windows")]
mod shared;
#[cfg(target_os="windows")]
mod engine;
#[cfg(target_os="windows")]
mod guest_gdb;

#[cfg(target_os="windows")]
fn main(){
 use std::{io::{BufRead,BufReader,Write},net::{TcpListener,TcpStream},
           sync::{Arc,Mutex},thread,time::Duration};
 use serde_json::{Value,json};
 type State=Arc<Mutex<engine::Engine>>;
 fn client(stream:TcpStream,state:State){
  let Ok(reader_stream)=stream.try_clone() else {return};
  let mut reader=BufReader::new(reader_stream);
  let mut writer=stream;
  let _=writer.set_write_timeout(Some(Duration::from_secs(2)));
  let _=reader.get_mut().set_read_timeout(Some(Duration::from_secs(30)));
  loop{
   let mut line=Vec::with_capacity(512);
   match reader.read_until(b'\n',&mut line){
    Ok(0)=>break,
    Ok(_)=>{
     if line.len()>4096{
      let _=writer.write_all(b"{\"error\":\"message too large\"}\n");
      break;
     }
     let response=match serde_json::from_slice::<Value>(&line){
      Ok(value)=>match state.lock(){
       Ok(mut engine)=>engine.command(value),
       Err(_)=>json!({"error":"shared bridge state poisoned"})
      },
      Err(err)=>json!({"error":format!("invalid JSON: {err}")})
     };
     let mut bytes=response.to_string().into_bytes();
     bytes.push(b'\n');
     if writer.write_all(&bytes).is_err(){break}
    }
    Err(e)=>{eprintln!("[RUST_BRIDGE] Client read error: {e}");break}
   }
  }
 }
 fn serve()->Result<(),Box<dyn std::error::Error>>{
  let state:State=Arc::new(Mutex::new(engine::Engine::new()?));
  let sender=Arc::clone(&state);
  thread::Builder::new().name("botwcraft-wxlm-transport".into())
    .spawn(move||guest_gdb::transport_loop(sender))?;
  let ticker=Arc::clone(&state);
  thread::Builder::new().name("botwcraft-bdp1".into()).spawn(move||{
   loop{
    if let Ok(mut engine)=ticker.lock(){engine.tick();}
    else {eprintln!("[RUST_BRIDGE] Sync state poisoned; stopping producer");return}
    thread::sleep(Duration::from_micros(16_667));
   }
  })?;
  let server=TcpListener::bind(("127.0.0.1",39847))?;
  println!("[RUST_BRIDGE] Minecraft protocol compatible TCP 127.0.0.1:39847");
  println!("[RUST_BRIDGE] SkyCraft_v1 memory + authoritative Minecraft pose producer ready");
  println!("[RUST_BRIDGE] Input ring remains owned by Rust compositor");
  println!("[RUST_BRIDGE] Ryujinx GDB guest transport enabled; requires port 22225 and LIVE guest ACK");
  println!("[RUST_BRIDGE] BOTW engine actor/camera hooks still required for actual gameplay");
  for conn in server.incoming(){
   match conn {
    Ok(stream)=>{let s=Arc::clone(&state);thread::spawn(move||client(stream,s));}
    Err(err)=>eprintln!("[RUST_BRIDGE] TCP accept error: {err}")
   }
  }
  Ok(())
 }
 if let Err(err)=serve(){eprintln!("[RUST_BRIDGE] FATAL: {err}");std::process::exit(1)}
}

#[cfg(not(target_os="windows"))]
fn main(){
 eprintln!("BotwCraft bridge requires Windows named memory mappings");
 std::process::exit(2);
}
