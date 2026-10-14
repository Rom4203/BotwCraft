"""Integration tests run using oead; synthetic map, no Nintendo copyrighted data."""
import tempfile
import unittest
from pathlib import Path
import oead
from place_box import build,ACTORS

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.base=Path(self.tmp.name)
  self.romfs=self.base/"original_romfs"
  self.map=self.romfs/"Map"/"MainField"/"I-7"/"I-7_Dynamic.smubin"
  self.map.parent.mkdir(parents=True)
  self.original=oead.byml.Hash({
   "Objs":oead.byml.Array([
     oead.byml.Hash({
      "HashId":oead.U32(i+123), "UnitConfigName":"Obj_Plant_CypressLow_B_01",
      "Translate":oead.byml.Array([oead.F32(3450.+i),oead.F32(226.),oead.F32(2140.+i)]),
      "SRTHash":oead.S32(1),
     }) for i in range(10)]),
   "Rails":oead.byml.Array([]),
  })
  binary=bytes(oead.byml.to_binary(self.original,big_endian=False,version=2))
  self.map.write_bytes(bytes(oead.yaz0.compress(binary,data_alignment=0x80)))
  self.orig_bytes=self.map.read_bytes()
 def test_actual_hyrule_box_generated_and_original_remains_untouched(self):
  mod=self.base/"test_world_actor"
  file,hid=build(self.romfs,(3452.,226.,2142.),mod,"wood")
  self.assertTrue(file.exists())
  self.assertEqual(file.relative_to(mod.resolve()).as_posix(),
     "romfs/Map/MainField/I-7/I-7_Dynamic.smubin")
  self.assertEqual(self.map.read_bytes(),self.orig_bytes)
  root=oead.byml.from_binary(oead.yaz0.decompress(file.read_bytes()))
  self.assertEqual(len(root["Objs"]),11)
  self.assertEqual(root["Rails"],self.original["Rails"])
  obj=next(o for o in root["Objs"] if int(o["HashId"])==hid)
  self.assertEqual(obj["UnitConfigName"],ACTORS["wood"])
  self.assertEqual([float(v) for v in obj["Translate"]],[3452.,226.,2142.])
  self.assertFalse(obj["IsStatic"])
  self.assertEqual([int(o["HashId"]) for o in root["Objs"]],
                   sorted(int(o["HashId"]) for o in root["Objs"]))
 def test_reject_unknown_region_instead_of_guessing(self):
  with self.assertRaises(RuntimeError):
   build(self.romfs,(-4000.,200.,-3500.),self.base/"output","wood")
 def test_no_game_original_overwrite(self):
  with self.assertRaises(ValueError):
   build(self.romfs,(3450.,226.,2140.),self.romfs)
 def test_iron_box_is_real_native_actor(self):
  file,hid=build(self.romfs,(3450.,226.,2141.),self.base/"mod","iron")
  root=oead.byml.from_binary(oead.yaz0.decompress(file.read_bytes()))
  entry=next(o for o in root["Objs"] if int(o["HashId"])==hid)
  self.assertEqual(entry["UnitConfigName"],"Obj_BreakBoxIron")
if __name__=="__main__":unittest.main()
