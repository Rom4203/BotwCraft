#include "native_direct_executor.hpp"
#include <cassert>

struct FakeGame {
    int physicsAndCamera = 0;
    int disarms = 0;
    BotwCraftDirect::Target last{};
};

static bool Apply(const BotwCraftDirect::Target& p, void* context) {
    auto* game=static_cast<FakeGame*>(context);
    game->last=p;
    game->physicsAndCamera++;
    return true;
}
static void Disarm(void* context) {
    static_cast<FakeGame*>(context)->disarms++;
}

int main() {
    using namespace BotwCraftDirect;
    FakeGame game;
    GameOps ops{&Apply,&Disarm,&game};
    Executor executor;
    Target target{};
    target.sequence=2;
    target.magic=kMagic;
    target.version=kVersion;
    target.flags=kActive|kFirstPerson;
    target.timeMs=1000;
    target.minecraftFrame=5;
    target.position[0]=-1125; target.position[1]=237; target.position[2]=1906;
    target.eye[0]=-1125; target.eye[1]=238.62; target.eye[2]=1906;
    target.forward[2]=1;
    assert(executor.Tick(target,2,2,1100,ops));
    assert(executor.applied==1);
    assert(game.physicsAndCamera==1);
    assert(game.last.position[0]==-1125);
    assert(game.last.eye[1]>238);
    assert(executor.Tick(target,2,2,1150,ops));
    assert(game.physicsAndCamera==1); // same Minecraft frame must not reapply
    target.sequence=4;
    target.minecraftFrame=6;
    target.position[0]=-1124;
    assert(executor.Tick(target,4,4,1180,ops));
    assert(game.physicsAndCamera==2);
    assert(game.last.position[0]==-1124);
    assert(!executor.Tick(target,5,5,1190,ops));
    assert(game.disarms==1);
    assert(!executor.engaged);
    target.sequence=6;
    target.minecraftFrame=7;
    assert(!executor.Tick(target,6,6,3001,ops));
    assert(game.disarms==1);
    executor.Stop(ops);
    return 0;
}
