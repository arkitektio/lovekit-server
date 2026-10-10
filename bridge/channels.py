from kante.channel import build_channel
from bridge.channel_signals import CallInviteSignal, CallSignal, StreamSignal

stream_channel = build_channel(StreamSignal)

# Named, so it never receives the stream channel's broadcasts. One group per
# invitee (`call_invite_channel.org_group(org, user.sub)`), on both sides.
call_invite_channel = build_channel(CallInviteSignal, name="call_invites")

# One group per organization (`call_group(org)`), on both sides: a call
# starting, or taking on a new topic, is news for everyone who may join it.
call_channel = build_channel(CallSignal, name="calls")
