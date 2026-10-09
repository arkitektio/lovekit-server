from kante.channel import build_channel
from bridge.channel_signals import CallInviteSignal, StreamSignal

stream_channel = build_channel(StreamSignal)

# Named, so it never receives the stream channel's broadcasts. One group per
# invitee (`call_invite_channel.org_group(org, user.sub)`), on both sides.
call_invite_channel = build_channel(CallInviteSignal, name="call_invites")
