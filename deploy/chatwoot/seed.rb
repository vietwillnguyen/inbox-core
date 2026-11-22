# Idempotent setup of one client's Chatwoot, run with `rails runner` inside the
# rails container by stack.sh. Made-up organisation and people only.
# Prints KEY=VALUE lines on stdout, which stack.sh writes to the gitignored
# .local/tokens.env. Nothing here is a real account.
admin_email = ENV.fetch('CHATWOOT_ADMIN_EMAIL')
admin_password = ENV.fetch('CHATWOOT_ADMIN_PASSWORD')
agent_email = ENV.fetch('CHATWOOT_AGENT_EMAIL')
agent_password = ENV.fetch('CHATWOOT_AGENT_PASSWORD')
bot_url = ENV.fetch('BOT_OUTGOING_URL')
tab_url = ENV.fetch('DASHBOARD_APP_URL')
widget_origin = ENV.fetch('WIDGET_ORIGIN')
fallback_text = ENV.fetch('FALLBACK_TEXT')

Redis::Alfred.delete(Redis::Alfred::CHATWOOT_INSTALLATION_ONBOARDING)

account = Account.find_or_create_by!(name: 'Brambleford Tool Library')

def person(email, password, name, type = nil)
  user = User.find_by(email: email)
  return user if user

  user = User.new(name: name, email: email, password: password)
  user.type = type if type
  user.skip_confirmation!
  user.save!
  user
end

admin = person(admin_email, admin_password, 'Example Admin', 'SuperAdmin')
agent = person(agent_email, agent_password, 'Example Volunteer')
AccountUser.find_or_create_by!(account: account, user: admin) { |au| au.role = :administrator }
AccountUser.find_or_create_by!(account: account, user: agent) { |au| au.role = :agent }

# The visitor sees the inbox's name in the widget header, so it is the organisation's.
inbox = account.inboxes.find_by(name: ['Website chat', 'Brambleford Tool Library'])
unless inbox
  widget = Channel::WebWidget.create!(account: account, website_url: widget_origin,
                                      welcome_title: 'Brambleford Tool Library',
                                      welcome_tagline: 'Ask about opening hours, borrowing and workshops.')
  inbox = Inbox.create!(account: account, name: 'Brambleford Tool Library', channel: widget)
end
inbox.update!(name: 'Brambleford Tool Library')
[admin, agent].each { |user| InboxMember.find_or_create_by!(user: user, inbox: inbox) }
# The email-collect prompt posts two template messages with a new conversation,
# and the bot receives those too. When this service is down, each failed
# delivery opens the conversation at the same moment and the fallback rule
# below fires once per opening, so the visitor gets the holding message three
# times. Without the prompt there is one delivery per visitor message.
inbox.update!(enable_email_collect: false)

# A second inbox the volunteer is not a member of, for the draft tab's access checks.
other = account.inboxes.find_by(name: 'Staff only')
unless other
  channel = Channel::Api.create!(account: account)
  other = Inbox.create!(account: account, name: 'Staff only', channel: channel)
end
InboxMember.find_or_create_by!(user: admin, inbox: other)

# The visitor sees the bot's name on every answer.
bot = AgentBot.find_by(account: account, name: ['inbox-core', 'Library assistant']) ||
      AgentBot.create!(account: account, name: 'Library assistant')
bot.update!(name: 'Library assistant', outgoing_url: bot_url,
            description: 'inbox-core: guard, triage, handle, deliver, hand off')
abi = AgentBotInbox.find_or_initialize_by(inbox: inbox)
abi.update!(account: account, agent_bot: bot, status: :active)

%w[inbox-core handoff draft-pending classifier-unavailable inbox-core-unavailable faq membership
   reservation damage_report donation press complaint other].each do |title|
  account.labels.find_or_create_by!(title: title)
end

app = DashboardApp.find_or_initialize_by(account: account, title: 'inbox-core drafts')
app.user ||= admin
app.content = [{ type: 'frame', url: tab_url }]
app.save!

# When this service is down, Chatwoot opens the conversation itself
# (lib/webhooks/trigger.rb) and tells the visitor nothing. This rule sends the
# visitor a holding message when a conversation is opened with no labels.
# inbox-core labels every conversation it processes ("inbox-core"), and labels
# a hand-off before it opens one, so an agent taking over a conversation the
# bot handled does not trigger it. What is left is a conversation the service
# never saw, opened by Chatwoot's bot-failure path (or by a person from the
# status menu). Conditions on the assignee do not work: inbox auto-assignment
# gives the conversation to an online agent as Chatwoot opens it.
rule = AutomationRule.find_or_initialize_by(account: account, name: 'inbox-core unavailable')
rule.update!(
  description: 'Holding message when the inbox-core service could not be reached',
  event_name: 'conversation_opened',
  active: true,
  conditions: [{ attribute_key: 'labels', filter_operator: 'is_not_present', values: [], query_operator: nil }],
  actions: [
    { action_name: 'send_message', action_params: [fallback_text] },
    { action_name: 'add_label', action_params: ['inbox-core-unavailable'] }
  ]
)

puts "CHATWOOT_ACCOUNT_ID=#{account.id}"
puts "CHATWOOT_INBOX_ID=#{inbox.id}"
puts "CHATWOOT_OTHER_INBOX_ID=#{other.id}"
puts "CHATWOOT_WEBSITE_TOKEN=#{inbox.channel.website_token}"
puts "CHATWOOT_BOT_TOKEN=#{bot.access_token.token}"
puts "CHATWOOT_BOT_SECRET=#{bot.secret}"
puts "CHATWOOT_ADMIN_TOKEN=#{admin.access_token.token}"
puts "CHATWOOT_ADMIN_USER_ID=#{admin.id}"
puts "CHATWOOT_AGENT_TOKEN=#{agent.access_token.token}"
puts "CHATWOOT_AGENT_USER_ID=#{agent.id}"
