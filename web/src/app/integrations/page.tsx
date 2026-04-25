"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, PluginInfo, RegistryEntry } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetFooter,
  SheetClose,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SchemaForm } from "@/components/plugin-settings";
import { FIESTABOARD_COLORS, AVAILABLE_COLORS, FiestaboardColorName } from "@/lib/board-colors";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import {
  Cloud,
  Calendar,
  Home,
  Wifi,
  Sparkles,
  Wind,
  TrainFront,
  Waves,
  Bike,
  Car,
  TrendingUp,
  Plane,
  Puzzle,
  Settings,
  AlertCircle,
  CheckCircle,
  XCircle,
  Sun,
  Moon,
  Thermometer,
  Droplets,
  Zap,
  Music,
  Film,
  Gamepad2,
  GitBranch,
  BookOpen,
  Coffee,
  ShoppingCart,
  DollarSign,
  Bitcoin,
  Globe,
  MapPin,
  Navigation,
  Clock,
  Bell,
  MessageSquare,
  Mail,
  Phone,
  Camera,
  Image,
  Video,
  Mic,
  Volume2,
  Heart,
  Star,
  Award,
  Trophy,
  Target,
  Activity,
  BarChart,
  PieChart,
  LineChart,
  Database,
  Server,
  Cpu,
  HardDrive,
  Smartphone,
  Laptop,
  Monitor,
  Tv,
  Radio,
  Headphones,
  Speaker,
  Battery,
  BatteryCharging,
  Power,
  Lightbulb,
  Fan,
  Thermometer as ThermometerIcon,
  Umbrella,
  CloudRain,
  CloudSnow,
  CloudSun,
  Sunrise,
  Sunset,
  Eye,
  EyeOff,
  Lock,
  Unlock,
  Key,
  Shield,
  ShieldCheck,
  ShieldAlert,
  UserCircle,
  Users,
  Building,
  Building2,
  Factory,
  Store,
  Warehouse,
  Package,
  Gift,
  Trash,
  Trash2,
  Recycle,
  Leaf,
  TreePine,
  Flower2,
  Bug,
  Fish,
  Bird,
  Dog,
  Cat,
  Footprints,
  Dumbbell,
  Pill,
  Stethoscope,
  Syringe,
  Ambulance,
  Flame,
  Snowflake,
  Anchor,
  Ship,
  Rocket,
  Satellite,
  Radio as RadioIcon,
  Rss,
  Wifi as WifiIcon,
  WifiOff,
  Bluetooth,
  NfcIcon,
  QrCode,
  Barcode,
  Fingerprint,
  ScanFace,
  Bot,
  Cog,
  Wrench,
  Hammer,
  PenTool,
  Brush,
  Palette,
  Scissors,
  Ruler,
  Calculator,
  Binary,
  Code,
  Terminal,
  FileCode,
  FolderOpen,
  Folder,
  File,
  FileText,
  FileImage,
  FileVideo,
  FileAudio,
  Download,
  Upload,
  RefreshCw,
  ArrowDownToLine,
  RotateCcw,
  Repeat,
  Shuffle,
  Play,
  Pause,
  SkipForward,
  SkipBack,
  FastForward,
  Rewind,
  Volume,
  VolumeX,
  Maximize,
  Minimize,
  Move,
  Copy,
  Clipboard,
  ClipboardCheck,
  Check,
  X,
  Plus,
  Minus,
  Divide,
  Equal,
  Hash,
  AtSign,
  Percent,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUp,
  ChevronsDown,
  CornerUpRight,
  ExternalLink,
  Link as LinkIcon,
  Link2,
  Unlink,
  Paperclip,
  Pin,
  MapPinned,
  Compass,
  Map,
  Route,
  Signpost,
  Flag,
  Bookmark,
  Tag,
  Tags,
  Search,
  Filter,
  SortAsc,
  SortDesc,
  List,
  Grid,
  LayoutGrid,
  LayoutList,
  Columns,
  Rows,
  Table,
  Kanban,
  Trello,
  Calendar as CalendarIcon,
  CalendarDays,
  CalendarClock,
  AlarmClock,
  Timer,
  Hourglass,
  Watch,
  History,
  Archive,
  Inbox,
  Send,
  Reply,
  Forward,
  CornerUpLeft,
  MessageCircle,
  MessagesSquare,
  AtSign as AtSignIcon,
  Megaphone,
  Newspaper,
  ScrollText,
  FileSpreadsheet,
  Presentation,
  GraduationCap,
  School,
  Library,
  Landmark,
  Church,
  Tent,
  Mountain,
  Trees,
  Flower,
  Sprout,
  Apple,
  Cherry,
  Grape,
  Banana,
  Carrot,
  Beef,
  Egg,
  Croissant,
  Pizza,
  Sandwich,
  Soup,
  IceCream,
  Cake,
  Cookie,
  CupSoda,
  Beer,
  Wine,
  Martini,
  GlassWater,
  Milk,
  CircleDot,
  Disc,
  CirclePlay,
  CirclePause,
  CircleStop,
  Square,
  Circle,
  Triangle,
  Pentagon,
  Hexagon,
  Octagon,
  Diamond,
  Spade,
  Club,
  Gem,
  Crown,
  Wand,
  Wand2,
  PartyPopper,
  Confetti,
  Cake as CakeIcon,
  Balloon,
  Ghost,
  Skull,
  Smile,
  Frown,
  Meh,
  Angry,
  Laugh,
  MoreHorizontal,
} from "lucide-react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";


/**
 * Comprehensive icon mapping from Lucide icon names to components.
 * Plugins can specify any of these icons in their manifest.json.
 */
const ICON_MAP: Record<string, LucideIcon> = {
  // Weather & Environment
  cloud: Cloud,
  sun: Sun,
  moon: Moon,
  thermometer: Thermometer,
  droplets: Droplets,
  wind: Wind,
  umbrella: Umbrella,
  cloud_rain: CloudRain,
  cloudrain: CloudRain,
  cloud_snow: CloudSnow,
  cloudsnow: CloudSnow,
  cloud_sun: CloudSun,
  cloudsun: CloudSun,
  sunrise: Sunrise,
  sunset: Sunset,
  snowflake: Snowflake,
  flame: Flame,
  waves: Waves,
  
  // Transportation
  car: Car,
  bike: Bike,
  train: TrainFront,
  train_front: TrainFront,
  trainfront: TrainFront,
  plane: Plane,
  ship: Ship,
  rocket: Rocket,
  anchor: Anchor,
  navigation: Navigation,
  map_pin: MapPin,
  mappin: MapPin,
  compass: Compass,
  map: Map,
  route: Route,
  signpost: Signpost,
  
  // Home & Smart Home
  home: Home,
  lightbulb: Lightbulb,
  fan: Fan,
  power: Power,
  battery: Battery,
  battery_charging: BatteryCharging,
  batterycharging: BatteryCharging,
  wifi: Wifi,
  wifi_off: WifiOff,
  wifioff: WifiOff,
  bluetooth: Bluetooth,
  lock: Lock,
  unlock: Unlock,
  key: Key,
  shield: Shield,
  shield_check: ShieldCheck,
  shieldcheck: ShieldCheck,
  
  // Time & Calendar
  calendar: Calendar,
  calendar_days: CalendarDays,
  calendardays: CalendarDays,
  calendar_clock: CalendarClock,
  calendarclock: CalendarClock,
  clock: Clock,
  alarm_clock: AlarmClock,
  alarmclock: AlarmClock,
  timer: Timer,
  hourglass: Hourglass,
  watch: Watch,
  history: History,
  
  // Finance
  trending_up: TrendingUp,
  trendingup: TrendingUp,
  dollar_sign: DollarSign,
  dollarsign: DollarSign,
  bitcoin: Bitcoin,
  bar_chart: BarChart,
  barchart: BarChart,
  pie_chart: PieChart,
  piechart: PieChart,
  line_chart: LineChart,
  linechart: LineChart,
  activity: Activity,
  
  // Entertainment
  sparkles: Sparkles,
  music: Music,
  film: Film,
  gamepad2: Gamepad2,
  tv: Tv,
  radio: Radio,
  headphones: Headphones,
  speaker: Speaker,
  volume2: Volume2,
  play: Play,
  pause: Pause,
  party_popper: PartyPopper,
  partypopper: PartyPopper,
  
  // Communication
  message_square: MessageSquare,
  messagesquare: MessageSquare,
  message_circle: MessageCircle,
  messagecircle: MessageCircle,
  mail: Mail,
  phone: Phone,
  bell: Bell,
  megaphone: Megaphone,
  send: Send,
  rss: Rss,
  
  // Technology
  smartphone: Smartphone,
  laptop: Laptop,
  monitor: Monitor,
  cpu: Cpu,
  hard_drive: HardDrive,
  harddrive: HardDrive,
  server: Server,
  database: Database,
  globe: Globe,
  code: Code,
  terminal: Terminal,
  bot: Bot,
  satellite: Satellite,
  qr_code: QrCode,
  qrcode: QrCode,
  
  // Health & Fitness
  heart: Heart,
  activity2: Activity,
  dumbbell: Dumbbell,
  pill: Pill,
  stethoscope: Stethoscope,
  ambulance: Ambulance,
  apple: Apple,
  
  // Nature
  leaf: Leaf,
  tree_pine: TreePine,
  treepine: TreePine,
  flower2: Flower2,
  flower: Flower,
  sprout: Sprout,
  mountain: Mountain,
  trees: Trees,
  bug: Bug,
  fish: Fish,
  bird: Bird,
  dog: Dog,
  cat: Cat,
  
  // Food & Drink
  coffee: Coffee,
  pizza: Pizza,
  cake: Cake,
  cookie: Cookie,
  ice_cream: IceCream,
  icecream: IceCream,
  beer: Beer,
  wine: Wine,
  glass_water: GlassWater,
  glasswater: GlassWater,
  cup_soda: CupSoda,
  cupsoda: CupSoda,
  
  // Places
  building: Building,
  building2: Building2,
  factory: Factory,
  store: Store,
  warehouse: Warehouse,
  school: School,
  library: Library,
  landmark: Landmark,
  church: Church,
  tent: Tent,
  
  // Shopping
  shopping_cart: ShoppingCart,
  shoppingcart: ShoppingCart,
  package: Package,
  gift: Gift,
  tag: Tag,
  tags: Tags,
  
  // Actions & UI
  settings: Settings,
  cog: Cog,
  wrench: Wrench,
  hammer: Hammer,
  search: Search,
  filter: Filter,
  refresh_cw: RefreshCw,
  refreshcw: RefreshCw,
  download: Download,
  upload: Upload,
  eye: Eye,
  eye_off: EyeOff,
  eyeoff: EyeOff,
  
  // Status
  check_circle: CheckCircle,
  checkcircle: CheckCircle,
  alert_circle: AlertCircle,
  alertcircle: AlertCircle,
  x_circle: XCircle,
  xcircle: XCircle,
  check: Check,
  x: X,
  
  // Miscellaneous
  star: Star,
  award: Award,
  trophy: Trophy,
  target: Target,
  flag: Flag,
  bookmark: Bookmark,
  pin: Pin,
  link: LinkIcon,
  external_link: ExternalLink,
  externallink: ExternalLink,
  user_circle: UserCircle,
  usercircle: UserCircle,
  users: Users,
  zap: Zap,
  gem: Gem,
  crown: Crown,
  wand: Wand,
  wand2: Wand2,
  ghost: Ghost,
  skull: Skull,
  smile: Smile,
  book_open: BookOpen,
  bookopen: BookOpen,
  newspaper: Newspaper,
  graduation_cap: GraduationCap,
  graduationcap: GraduationCap,
  camera: Camera,
  image: Image,
  video: Video,
  mic: Mic,
  
  // Default fallback
  puzzle: Puzzle,
};

/**
 * Get the Lucide icon component for a plugin based on its manifest icon field.
 * Falls back to Puzzle icon if not found.
 */
function getPluginIcon(iconName?: string): LucideIcon {
  if (!iconName) return Puzzle;
  
  // Normalize: lowercase and handle both snake_case and lowercase
  const normalized = iconName.toLowerCase().replace(/-/g, '_');
  
  return ICON_MAP[normalized] || Puzzle;
}

// Color display helpers - using board's official colors
const COLOR_DISPLAY: Record<FiestaboardColorName, { bg: string; text: string; hex: string }> = {
  red: { bg: "bg-board-red", text: "text-board-white", hex: FIESTABOARD_COLORS.red },
  orange: { bg: "bg-board-orange", text: "text-board-black", hex: FIESTABOARD_COLORS.orange },
  yellow: { bg: "bg-board-yellow", text: "text-board-black", hex: FIESTABOARD_COLORS.yellow },
  green: { bg: "bg-board-green", text: "text-board-black", hex: FIESTABOARD_COLORS.green },
  blue: { bg: "bg-board-blue", text: "text-board-white", hex: FIESTABOARD_COLORS.blue },
  violet: { bg: "bg-board-violet", text: "text-board-white", hex: FIESTABOARD_COLORS.violet },
  white: { bg: "bg-board-white border", text: "text-board-black", hex: FIESTABOARD_COLORS.white },
  black: { bg: "bg-board-black", text: "text-board-white", hex: FIESTABOARD_COLORS.black },
};

// Available conditions for color rules
const AVAILABLE_CONDITIONS = [
  { value: ">=", label: ">= (greater or equal)" },
  { value: "<=", label: "<= (less or equal)" },
  { value: ">", label: "> (greater than)" },
  { value: "<", label: "< (less than)" },
  { value: "==", label: "== (equals)" },
  { value: "!=", label: "!= (not equals)" },
];

// Color rule types
interface ColorRule {
  condition: string;
  value: string | number;
  color: string;
}

interface ColorRulesConfig {
  [fieldName: string]: ColorRule[];
}

// Color Rules Editor Component
function ColorRulesEditor({
  pluginId,
  colorRules,
  onChange,
  onCopyVar,
  copiedVar,
}: {
  pluginId: string;
  colorRules: ColorRulesConfig;
  onChange: (rules: ColorRulesConfig) => void;
  onCopyVar: (varName: string) => void;
  copiedVar: string | null;
}) {
  const [newFieldName, setNewFieldName] = useState("");
  const [showAddField, setShowAddField] = useState(false);

  const handleUpdateRule = (fieldName: string, ruleIndex: number, updates: Partial<ColorRule>) => {
    const newRules = { ...colorRules };
    newRules[fieldName] = [...newRules[fieldName]];
    newRules[fieldName][ruleIndex] = { ...newRules[fieldName][ruleIndex], ...updates };
    onChange(newRules);
  };

  const handleDeleteRule = (fieldName: string, ruleIndex: number) => {
    const newRules = { ...colorRules };
    newRules[fieldName] = newRules[fieldName].filter((_, i) => i !== ruleIndex);
    if (newRules[fieldName].length === 0) {
      delete newRules[fieldName];
    }
    onChange(newRules);
  };

  const handleAddRule = (fieldName: string) => {
    const newRules = { ...colorRules };
    if (!newRules[fieldName]) {
      newRules[fieldName] = [];
    }
    newRules[fieldName] = [...newRules[fieldName], { condition: ">=", value: 0, color: "green" }];
    onChange(newRules);
  };

  const handleMoveRule = (fieldName: string, ruleIndex: number, direction: "up" | "down") => {
    const newRules = { ...colorRules };
    const rules = [...newRules[fieldName]];
    const newIndex = direction === "up" ? ruleIndex - 1 : ruleIndex + 1;
    if (newIndex < 0 || newIndex >= rules.length) return;
    [rules[ruleIndex], rules[newIndex]] = [rules[newIndex], rules[ruleIndex]];
    newRules[fieldName] = rules;
    onChange(newRules);
  };

  const handleAddField = () => {
    if (!newFieldName.trim()) return;
    const newRules = { ...colorRules };
    newRules[newFieldName.trim()] = [{ condition: ">=", value: 0, color: "green" }];
    onChange(newRules);
    setNewFieldName("");
    setShowAddField(false);
  };

  const handleDeleteField = (fieldName: string) => {
    const newRules = { ...colorRules };
    delete newRules[fieldName];
    onChange(newRules);
  };

  const fieldNames = Object.keys(colorRules);

  return (
    <TooltipProvider>
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-muted-foreground">
          Dynamic Colors
          <span className="ml-2 text-xs font-normal">(first match wins)</span>
        </h4>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => setShowAddField(!showAddField)}
        >
          <Plus className="h-3 w-3 mr-1" />
          Add Field
        </Button>
      </div>

      {/* Add new field input */}
      {showAddField && (
        <div className="flex gap-2 p-2 rounded-md border bg-muted/30">
          <input
            type="text"
            value={newFieldName}
            onChange={(e) => setNewFieldName(e.target.value)}
            placeholder="Field name (e.g., temperature)"
            className="flex-1 h-8 px-2 text-xs rounded border bg-background"
          />
          <Button size="sm" className="h-8 text-xs" onClick={handleAddField}>
            Add
          </Button>
          <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setShowAddField(false)}>
            Cancel
          </Button>
        </div>
      )}

      {fieldNames.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">
          No color rules configured. Add a field to create dynamic colors.
        </p>
      ) : (
        <div className="space-y-3">
          {fieldNames.map((fieldName) => {
            const rules = colorRules[fieldName];
            return (
              <div key={fieldName} className="rounded-md border overflow-hidden">
                {/* Field header */}
                <div className="bg-muted/50 px-3 py-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <code className="text-xs font-mono text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                      {pluginId}.{fieldName}
                    </code>
                    <span className="text-xs text-muted-foreground">→ color based on value</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => onCopyVar(`${fieldName}_color`)}
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-muted"
                    >
                      {copiedVar === `${fieldName}_color` ? (
                        <Check className="h-3 w-3 text-success" />
                      ) : (
                        <Copy className="h-3 w-3" />
                      )}
                      <code className="font-mono text-[10px]">{fieldName}_color</code>
                    </button>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => handleDeleteField(fieldName)}
                          className="p-1 text-destructive hover:bg-destructive/10 rounded"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Delete all rules for this field</p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </div>

                {/* Rules */}
                <div className="divide-y">
                  {rules.map((rule, idx) => {
                    const colorStyle = COLOR_DISPLAY[rule.color as FiestaboardColorName] || { bg: "bg-muted", text: "text-muted-foreground", hex: "#6b7280" };
                    return (
                      <div key={idx} className="px-3 py-2 flex items-center gap-2 text-xs">
                        {/* Reorder buttons */}
                        <div className="flex flex-col gap-0.5">
                          <button
                            onClick={() => handleMoveRule(fieldName, idx, "up")}
                            disabled={idx === 0}
                            className="p-0.5 hover:bg-muted rounded disabled:opacity-50"
                          >
                            <ArrowUp className="h-3 w-3" />
                          </button>
                          <button
                            onClick={() => handleMoveRule(fieldName, idx, "down")}
                            disabled={idx === rules.length - 1}
                            className="p-0.5 hover:bg-muted rounded disabled:opacity-50"
                          >
                            <ArrowDown className="h-3 w-3" />
                          </button>
                        </div>

                        {/* Color picker */}
                        <select
                          value={rule.color}
                          onChange={(e) => handleUpdateRule(fieldName, idx, { color: e.target.value })}
                          className="h-7 px-2 rounded border text-xs font-medium"
                          style={{ backgroundColor: colorStyle.hex, color: colorStyle.text === "text-board-black" ? "#000" : "#fff" }}
                        >
                          {AVAILABLE_COLORS.map((color) => (
                            <option key={color} value={color} className="bg-background text-foreground">
                              {color}
                            </option>
                          ))}
                        </select>

                        <span className="text-muted-foreground shrink-0">when</span>

                        {/* Condition picker */}
                        <select
                          value={rule.condition}
                          onChange={(e) => handleUpdateRule(fieldName, idx, { condition: e.target.value })}
                          className="h-7 px-2 rounded border bg-background text-xs font-mono"
                        >
                          {AVAILABLE_CONDITIONS.map((cond) => (
                            <option key={cond.value} value={cond.value}>
                              {cond.value}
                            </option>
                          ))}
                        </select>

                        {/* Value input */}
                        <input
                          type="text"
                          value={rule.value}
                          onChange={(e) => {
                            const val = e.target.value;
                            // Try to parse as number, otherwise keep as string
                            const numVal = parseFloat(val);
                            handleUpdateRule(fieldName, idx, { 
                              value: isNaN(numVal) ? val : numVal 
                            });
                          }}
                          className="w-20 h-7 px-2 rounded border bg-background text-xs font-mono"
                          placeholder="value"
                        />

                        {/* Delete button */}
                        <button
                          onClick={() => handleDeleteRule(fieldName, idx)}
                          className="p-1 text-destructive hover:bg-destructive/10 rounded ml-auto"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    );
                  })}
                </div>

                {/* Add rule button */}
                <div className="px-3 py-2 border-t bg-muted/20">
                  <button
                    onClick={() => handleAddRule(fieldName)}
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                  >
                    <Plus className="h-3 w-3" />
                    Add rule
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Rules are evaluated in order (first match wins). Use <code className="bg-muted px-1 rounded">{`{{${pluginId}.field_color}}`}</code> for just the color tile.
      </p>
    </div>
    </TooltipProvider>
  );
}

// Category labels
const CATEGORY_LABELS: Record<string, string> = {
  art: "Display Art",
  data: "Data & Information",
  entertainment: "Entertainment",
  finance: "Finance",
  home: "Smart Home",
  transit: "Transportation",
  utility: "Utilities",
  weather: "Weather & Environment",
};

interface PluginCardProps {
  plugin: PluginInfo;
  onToggle: (pluginId: string, enabled: boolean) => void;
  isToggling: boolean;
  onConfigUpdate: () => void;
  onUninstall?: (pluginId: string) => void;
  onUpdate?: (pluginId: string) => void;
  isUninstalling?: boolean;
  isUpdating?: boolean;
}

function PluginCard({
  plugin,
  onToggle,
  isToggling,
  onConfigUpdate,
  onUninstall,
  onUpdate,
  isUninstalling,
  isUpdating,
}: PluginCardProps) {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [copiedVar, setCopiedVar] = useState<string | null>(null);
  const [isCreatingDemo, setIsCreatingDemo] = useState(false);
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);

  const isExternal = plugin.source?.source_type !== "builtin";
  const hasUpdate = plugin.update_available === true;

  // Fetch plugin details when opening config
  const { data: pluginDetails, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["plugin", plugin.id],
    queryFn: () => api.getPlugin(plugin.id),
    enabled: isConfigOpen,
  });

  // Initialize config values when plugin details load
  useEffect(() => {
    if (pluginDetails?.config) {
      setConfigValues(pluginDetails.config);
    }
  }, [pluginDetails]);

  const handleSaveConfig = async () => {
    setIsSaving(true);
    try {
      await api.updatePluginConfig(plugin.id, configValues);
      toast.success(`${plugin.name} configuration saved`);
      onConfigUpdate();
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setIsConfigOpen(false);
    } catch (error) {
      toast.error(`Failed to save configuration: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setIsSaving(false);
    }
  };

  const queryClient = useQueryClient();

  const handleCreateDemoPage = async () => {
    setIsCreatingDemo(true);
    try {
      const result = await api.createPluginDemoPage(plugin.id);
      const verb = result.status === "recreated" ? "recreated" : "created";
      toast.success(`Demo page ${verb} for ${plugin.name}`);
      queryClient.invalidateQueries({ queryKey: ["plugin", plugin.id] });
      queryClient.invalidateQueries({ queryKey: ["pages"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setShowDemoConfirm(false);
    } catch (error) {
      toast.error(
        `Failed to create demo page: ${error instanceof Error ? error.message : "Unknown error"}`
      );
    } finally {
      setIsCreatingDemo(false);
    }
  };

  // Copy template variable
  const handleCopyVar = (varName: string) => {
    const templateVar = `{{${plugin.id}.${varName}}}`;
    navigator.clipboard.writeText(templateVar);
    setCopiedVar(varName);
    setTimeout(() => setCopiedVar(null), 2000);
    toast.success(`Copied ${templateVar}`);
  };

  const areDemoRequirementsMet = (): boolean => {
    if (!pluginDetails?.settings_schema) return true;
    const schema = pluginDetails.settings_schema as {
      required?: string[];
      properties?: Record<string, { type?: string }>;
    };
    const required = schema.required ?? [];
    const config = pluginDetails.config ?? {};
    return required.every(
      (field) => field === "enabled" || Boolean(config[field])
    );
  };

  // Parse variables from plugin details - handles both array and object formats for variables.simple
  const getVariablesList = () => {
    if (!pluginDetails?.variables) return [];
    const variables = pluginDetails.variables as {
      simple?: string[] | Record<string, { description?: string; max_length?: number; group?: string; example?: string }>;
      arrays?: Record<string, { label_field: string; item_fields: string[] }>;
    };
    const list: Array<{ name: string; description: string; maxChars: number }> = [];

    if (variables.simple) {
      if (Array.isArray(variables.simple)) {
        variables.simple.forEach(name => {
          list.push({
            name,
            description: name.replace(/_/g, ' '),
            maxChars: pluginDetails.max_lengths?.[name] ?? 22,
          });
        });
      } else {
        Object.entries(variables.simple).forEach(([name, meta]) => {
          list.push({
            name,
            description: meta.description ?? name.replace(/_/g, ' '),
            maxChars: pluginDetails.max_lengths?.[name] ?? meta.max_length ?? 22,
          });
        });
      }
    }

    if (variables.arrays) {
      Object.entries(variables.arrays).forEach(([arrayName, config]) => {
        list.push({
          name: `${arrayName}.{index}.${config.label_field}`,
          description: `${arrayName} label`,
          maxChars: pluginDetails.max_lengths?.[`${arrayName}.${config.label_field}`] ?? 22,
        });
        // Skip label_field in item_fields to avoid duplicate keys
        config.item_fields
          .filter(field => field !== config.label_field)
          .forEach(field => {
            list.push({
              name: `${arrayName}.{index}.${field}`,
              description: `${arrayName} ${field.replace(/_/g, ' ')}`,
              maxChars: pluginDetails.max_lengths?.[`${arrayName}.${field}`] ?? 22,
            });
          });
      });
    }

    return list;
  };

  // Use icon from plugin manifest, falling back to Puzzle
  const Icon = getPluginIcon(plugin.icon);

  const sourceType = plugin.source?.source_type;
  // "external" is what the backend returns for registry installs cloned to external_plugins/
  // "git" is what the backend returns for custom git URL installs
  const isMarketplace = sourceType === "registry" || sourceType === "external";
  const isGitExternal = sourceType === "git";
  const categoryLabel = CATEGORY_LABELS[plugin.category || "utility"] || plugin.category || "Utility";

  const configSheet = (
    <Sheet open={isConfigOpen} onOpenChange={setIsConfigOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="h-7 w-7">
          <Settings className="h-3.5 w-3.5" />
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Icon className="h-5 w-5" />
            {plugin.name}
          </SheetTitle>
          <SheetDescription>
            Configure settings for this integration
          </SheetDescription>
        </SheetHeader>
        <div className="py-6 space-y-6">
          {isLoadingDetails ? (
            <div className="space-y-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              {/* Demo Page Section */}
              {pluginDetails?.has_demo && (
                <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-medium">Demo Page</h4>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {pluginDetails.demo_page_id
                          ? "A demo page already exists for this plugin."
                          : "Create a ready-to-use page that showcases this plugin."}
                      </p>
                    </div>
                    {pluginDetails.demo_page_id ? (
                      <Dialog open={showDemoConfirm} onOpenChange={setShowDemoConfirm}>
                        <DialogTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!areDemoRequirementsMet() || isCreatingDemo}
                          >
                            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                            Recreate
                          </Button>
                        </DialogTrigger>
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle>Recreate Demo Page?</DialogTitle>
                            <DialogDescription>
                              This will delete the existing demo page and create a
                              fresh one with default settings. This action cannot be
                              undone.
                            </DialogDescription>
                          </DialogHeader>
                          <DialogFooter>
                            <Button
                              variant="outline"
                              onClick={() => setShowDemoConfirm(false)}
                            >
                              Cancel
                            </Button>
                            <Button
                              onClick={handleCreateDemoPage}
                              disabled={isCreatingDemo}
                            >
                              {isCreatingDemo ? "Creating..." : "Recreate Demo Page"}
                            </Button>
                          </DialogFooter>
                        </DialogContent>
                      </Dialog>
                    ) : (
                      <Button
                        variant="default"
                        size="sm"
                        onClick={handleCreateDemoPage}
                        disabled={!areDemoRequirementsMet() || isCreatingDemo}
                      >
                        <Play className="h-3.5 w-3.5 mr-1.5" />
                        {isCreatingDemo ? "Creating..." : "Create Demo Page"}
                      </Button>
                    )}
                  </div>
                  {!areDemoRequirementsMet() && (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      Configure the required settings below before creating a demo page.
                    </p>
                  )}
                </div>
              )}

              {/* Settings Section */}
              {pluginDetails?.settings_schema && Object.keys(pluginDetails.settings_schema.properties || {}).length > 0 && (
                <div className="space-y-4">
                  <h4 className="text-sm font-medium text-muted-foreground">Settings</h4>
                  <SchemaForm
                    schema={pluginDetails.settings_schema}
                    values={configValues}
                    onChange={setConfigValues}
                    disabled={isSaving}
                  />
                </div>
              )}

              {/* Template Variables Section */}
              {getVariablesList().length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-medium text-muted-foreground">
                    Template Variables
                    <span className="ml-2 text-xs font-normal">(click to copy)</span>
                  </h4>
                  <div className="rounded-md border overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">Variable</th>
                          <th className="text-left px-3 py-2 font-medium">Description</th>
                          <th className="text-center px-3 py-2 font-medium">Max</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {getVariablesList().map((variable) => (
                          <tr
                            key={variable.name}
                            className="hover:bg-muted/30 cursor-pointer transition-colors"
                            onClick={() => handleCopyVar(variable.name)}
                          >
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-1.5">
                                <code className="text-primary font-mono bg-primary/10 px-1.5 py-0.5 rounded text-[11px]">
                                  {plugin.id}.{variable.name}
                                </code>
                                {copiedVar === variable.name ? (
                                  <Check className="h-3 w-3 text-success" />
                                ) : (
                                  <Copy className="h-3 w-3 text-muted-foreground" />
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-muted-foreground capitalize">
                              {variable.description}
                            </td>
                            <td className="px-3 py-2 text-center">
                              <Badge variant="outline" className="text-[10px]">
                                {variable.maxChars}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Use in templates as <code className="bg-muted px-1 rounded">{`{{${plugin.id}.variable}}`}</code>
                  </p>
                </div>
              )}

              {/* Environment Variables Section */}
              {pluginDetails?.env_vars && pluginDetails.env_vars.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-medium text-muted-foreground">
                    Environment Variables
                  </h4>
                  <div className="rounded-md border overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">Variable</th>
                          <th className="text-left px-3 py-2 font-medium">Description</th>
                          <th className="text-center px-3 py-2 font-medium">Required</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {pluginDetails.env_vars.map((envVar) => (
                          <tr key={envVar.name} className="hover:bg-muted/30">
                            <td className="px-3 py-2">
                              <code className="font-mono bg-muted px-1.5 py-0.5 rounded text-[11px]">
                                {envVar.name}
                              </code>
                            </td>
                            <td className="px-3 py-2 text-muted-foreground">
                              {envVar.description}
                            </td>
                            <td className="px-3 py-2 text-center">
                              {envVar.required ? (
                                <Badge variant="destructive" className="text-[10px]">Required</Badge>
                              ) : (
                                <Badge variant="outline" className="text-[10px]">Optional</Badge>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Color Rules Section */}
              <ColorRulesEditor
                pluginId={plugin.id}
                colorRules={(configValues.color_rules as ColorRulesConfig) || {}}
                onChange={(newRules) => {
                  setConfigValues((prev) => ({ ...prev, color_rules: newRules }));
                }}
                onCopyVar={handleCopyVar}
                copiedVar={copiedVar}
              />

              {/* No config message */}
              {(!pluginDetails?.settings_schema || Object.keys(pluginDetails.settings_schema.properties || {}).length === 0) &&
               getVariablesList().length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No configuration options available for this plugin.
                </p>
              )}
            </>
          )}
        </div>
        <SheetFooter className="flex-col gap-2 sm:flex-row">
          {isExternal && onUninstall && (
            <Button
              variant="destructive"
              className="sm:mr-auto"
              size="sm"
              onClick={() => {
                setIsConfigOpen(false);
                onUninstall(plugin.id);
              }}
              disabled={isUninstalling}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              {isUninstalling ? "Uninstalling..." : "Uninstall"}
            </Button>
          )}
          <SheetClose asChild>
            <Button variant="outline" disabled={isSaving}>
              Cancel
            </Button>
          </SheetClose>
          <Button onClick={handleSaveConfig} disabled={isSaving || isLoadingDetails}>
            {isSaving ? "Saving..." : "Save Changes"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );

  return (
    <tr className={cn(
      "border-b last:border-b-0 transition-colors",
      plugin.enabled ? "hover:bg-muted/30" : "opacity-60 hover:opacity-80 hover:bg-muted/20"
    )}>
      {/* Name column: icon + name + version + source badges */}
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className={cn(
            "p-1.5 rounded-md shrink-0",
            plugin.enabled ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
          )}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap min-w-0">
            <span className="font-medium text-sm whitespace-nowrap">{plugin.name}</span>
            <Badge variant="outline" className="text-[10px] font-normal px-1.5 py-0 h-4 shrink-0">
              v{plugin.version}
            </Badge>
            {isMarketplace && (
              <Badge variant="outline" className="text-[10px] gap-1 font-normal px-1.5 py-0 h-4 shrink-0 border-sky-300 text-sky-600 dark:text-sky-400 dark:border-sky-700">
                <Package className="h-2.5 w-2.5" />
                Marketplace
              </Badge>
            )}
            {isGitExternal && (
              <Badge variant="outline" className="text-[10px] gap-1 font-normal px-1.5 py-0 h-4 shrink-0 border-purple-300 text-purple-600 dark:text-purple-400 dark:border-purple-700">
                <GitBranch className="h-2.5 w-2.5" />
                External
              </Badge>
            )}
            {hasUpdate && (
              <Badge variant="outline" className="text-[10px] gap-1 font-normal px-1.5 py-0 h-4 shrink-0 text-amber-600 border-amber-300 bg-amber-50 dark:bg-amber-950 dark:text-amber-400">
                <ArrowDownToLine className="h-2.5 w-2.5" />
                Update
              </Badge>
            )}
          </div>
        </div>
      </td>

      {/* Category column */}
      <td className="px-4 py-2.5 text-sm text-muted-foreground whitespace-nowrap hidden sm:table-cell">
        {categoryLabel}
      </td>

      {/* Status column */}
      <td className="px-4 py-2.5 whitespace-nowrap hidden md:table-cell">
        {plugin.enabled ? (
          plugin.configured ? (
            <Badge variant="default" className="text-[10px] gap-1 px-1.5 py-0 h-5">
              <CheckCircle className="h-2.5 w-2.5" />
              Configured
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-[10px] gap-1 px-1.5 py-0 h-5">
              <AlertCircle className="h-2.5 w-2.5" />
              Setup Required
            </Badge>
          )
        ) : (
          <Badge variant="outline" className="text-[10px] gap-1 px-1.5 py-0 h-5">
            <XCircle className="h-2.5 w-2.5" />
            Disabled
          </Badge>
        )}
      </td>

      {/* Actions column: toggle + configure + overflow */}
      <td className="px-4 py-2.5">
        <div className="flex items-center justify-end gap-0.5">
          <Switch
            checked={plugin.enabled}
            onCheckedChange={(checked) => onToggle(plugin.id, checked)}
            disabled={isToggling}
            aria-label={`Toggle ${plugin.name}`}
          />
          {configSheet}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7">
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setIsConfigOpen(true)}>
                <Settings className="h-3.5 w-3.5 mr-2" />
                Configure
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onToggle(plugin.id, !plugin.enabled)} disabled={isToggling}>
                {plugin.enabled ? (
                  <XCircle className="h-3.5 w-3.5 mr-2" />
                ) : (
                  <CheckCircle className="h-3.5 w-3.5 mr-2" />
                )}
                {plugin.enabled ? "Disable" : "Enable"}
              </DropdownMenuItem>
              {hasUpdate && onUpdate && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => onUpdate(plugin.id)} disabled={isUpdating}>
                    <RefreshCw className={cn("h-3.5 w-3.5 mr-2", isUpdating && "animate-spin")} />
                    {isUpdating ? "Updating..." : "Update"}
                  </DropdownMenuItem>
                </>
              )}
              {isExternal && onUninstall && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => onUninstall(plugin.id)}
                    disabled={isUninstalling}
                    className="text-destructive focus:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-2" />
                    {isUninstalling ? "Uninstalling..." : "Uninstall"}
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </td>
    </tr>
  );
}

function RegistryPluginCard({
  entry,
  onInstall,
  isInstalling,
  index = 0,
}: {
  entry: RegistryEntry;
  onInstall: (pluginId: string) => void;
  isInstalling: boolean;
  index?: number;
}) {
  const Icon = getPluginIcon(entry.icon);
  return (
    <div className="rounded-xl animate-card-fade-in h-full" style={{ animationDelay: `${index * 60}ms` }}>
      <Link href={`/integrations/${entry.id}`} className="block h-full group">
        <Card className="opacity-60 group-hover:opacity-90 transition-opacity border-dashed h-full flex flex-col">
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-muted text-muted-foreground shrink-0">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle className="text-base">{entry.name}</CardTitle>
                  <CardDescription className="text-xs mt-0.5">by {entry.author}</CardDescription>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs shrink-0"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onInstall(entry.id); }}
                disabled={isInstalling}
              >
                <ArrowDownToLine className={cn("h-3 w-3 mr-1", isInstalling && "animate-bounce")} />
                {isInstalling ? "Installing..." : "Install"}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="pt-0 flex flex-col flex-1">
            <p className="text-sm text-muted-foreground mb-3 line-clamp-2 flex-1">{entry.description}</p>
            <Badge variant="secondary" className="text-xs gap-1 self-start">
              {CATEGORY_LABELS[entry.category || "utility"] || entry.category || "Utility"}
            </Badge>
          </CardContent>
        </Card>
      </Link>
    </div>
  );
}

function RegistryPluginRow({
  entry,
  onInstall,
  isInstalling,
}: {
  entry: RegistryEntry;
  onInstall: (pluginId: string) => void;
  isInstalling: boolean;
}) {
  const Icon = getPluginIcon(entry.icon);
  return (
    <tr className="border-b last:border-b-0 hover:bg-muted/30 transition-colors">
      <td className="px-4 py-2.5">
        <Link href={`/integrations/${entry.id}`} className="flex items-center gap-3 group">
          <div className="p-1.5 rounded-md bg-muted text-muted-foreground shrink-0">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <span className="font-medium text-sm group-hover:underline underline-offset-2">{entry.name}</span>
            {entry.description && (
              <p className="text-xs text-muted-foreground truncate max-w-xs">{entry.description}</p>
            )}
          </div>
        </Link>
      </td>
      <td className="px-4 py-2.5 text-sm text-muted-foreground whitespace-nowrap">
        {CATEGORY_LABELS[entry.category || "utility"] || entry.category || "Utility"}
      </td>
      <td className="px-4 py-2.5 text-sm text-muted-foreground whitespace-nowrap">
        {entry.author}
      </td>
      <td className="px-4 py-2.5 text-right">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => onInstall(entry.id)}
          disabled={isInstalling}
        >
          <ArrowDownToLine className={cn("h-3 w-3 mr-1", isInstalling && "animate-bounce")} />
          {isInstalling ? "Installing..." : "Install"}
        </Button>
      </td>
    </tr>
  );
}


export default function IntegrationsPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState(() => {
    const tab = searchParams.get("tab");
    return tab === "marketplace" || tab === "installed" ? tab : "installed";
  });
  const [marketplaceView, setMarketplaceView] = useState<"card" | "list">("card");
  const [marketplaceSort, setMarketplaceSort] = useState<{ key: "name" | "category" | "author"; dir: "asc" | "desc" }>({ key: "name", dir: "asc" });
  const [installedSort, setInstalledSort] = useState<{ key: "name" | "category" | "status"; dir: "asc" | "desc" }>({ key: "name", dir: "asc" });
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [isUpdatingAll, setIsUpdatingAll] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [gitDialogOpen, setGitDialogOpen] = useState(false);
  const [gitUrl, setGitUrl] = useState("");
  const [gitPluginId, setGitPluginId] = useState("");
  const [gitBranch, setGitBranch] = useState("");
  const [isInstallingGit, setIsInstallingGit] = useState(false);

  // Fetch installed plugins list
  const { data, isLoading, error } = useQuery({
    queryKey: ["plugins"],
    queryFn: api.listPlugins,
  });

  // Fetch registry (available but not necessarily installed)
  const { data: registryData } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
  });

  // Toggle plugin mutation
  const toggleMutation = useMutation({
    mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
      if (enabled) {
        return api.enablePlugin(pluginId);
      } else {
        return api.disablePlugin(pluginId);
      }
    },
    onMutate: async ({ pluginId, enabled }) => {
      await queryClient.cancelQueries({ queryKey: ["plugins"] });
      const previousPlugins = queryClient.getQueryData(["plugins"]);
      queryClient.setQueryData(["plugins"], (old: typeof data) => {
        if (!old) return old;
        return {
          ...old,
          plugins: old.plugins.map((p: PluginInfo) =>
            p.id === pluginId ? { ...p, enabled } : p
          ),
          enabled_count: enabled
            ? old.enabled_count + 1
            : old.enabled_count - 1,
        };
      });
      return { previousPlugins };
    },
    onError: (err, { pluginId }, context) => {
      queryClient.setQueryData(["plugins"], context?.previousPlugins);
      toast.error(`Failed to toggle ${pluginId}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    },
    onSuccess: (_, { pluginId, enabled }) => {
      toast.success(`${pluginId} ${enabled ? 'enabled' : 'disabled'}`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["plugins"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["template-variables"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: 'active' });
    },
  });

  const handleToggle = (pluginId: string, enabled: boolean) => {
    toggleMutation.mutate({ pluginId, enabled });
  };

  const handleInstall = async (pluginId: string) => {
    setInstallingId(pluginId);
    try {
      await api.installRegistryPlugin(pluginId);
      await api.enablePlugin(pluginId);
      toast.success(`${pluginId} installed and enabled`);
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setActiveTab("installed");
    } catch (err) {
      toast.error(`Failed to install ${pluginId}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setInstallingId(null);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    setUninstallingId(pluginId);
    try {
      await api.uninstallPlugin(pluginId);
      toast.success(`${pluginId} uninstalled`);
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    } catch (err) {
      toast.error(`Failed to uninstall ${pluginId}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setUninstallingId(null);
    }
  };

  const handleUpdate = async (pluginId: string) => {
    setUpdatingId(pluginId);
    try {
      await api.updatePlugin(pluginId);
      toast.success(`${pluginId} updated successfully`);
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    } catch (err) {
      toast.error(`Failed to update ${pluginId}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleUpdateAll = async () => {
    setIsUpdatingAll(true);
    try {
      const result = await api.applyAllPluginUpdates();
      if (result.updated.length > 0) {
        toast.success(`Updated ${result.updated.length} plugin(s)`);
      }
      const failedIds = Object.keys(result.failed);
      if (failedIds.length > 0) {
        toast.error(`${failedIds.length} plugin(s) failed to update: ${failedIds.join(", ")}`);
      }
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    } catch (err) {
      toast.error(`Update all failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsUpdatingAll(false);
    }
  };

  const handleInstallFromGit = async () => {
    if (!gitUrl.trim()) return;
    setIsInstallingGit(true);
    try {
      const result = await api.installGitPlugin(
        gitUrl.trim(),
        gitPluginId.trim() || undefined,
        gitBranch.trim() || undefined,
      );
      toast.success(`${result.plugin_id} installed from git`);
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setGitDialogOpen(false);
      setActiveTab("installed");
      setGitUrl("");
      setGitPluginId("");
      setGitBranch("");
    } catch (err) {
      toast.error(`Failed to install: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsInstallingGit(false);
    }
  };

  // Build a merged view: installed plugins + uninstalled registry entries
  const installedIds = new Set(data?.plugins.map((p) => p.id) ?? []);
  const uninstalledRegistry = (registryData?.entries ?? []).filter(
    (e) => !installedIds.has(e.id)
  );

  const query = searchQuery.toLowerCase().trim();

  const filteredInstalled = (data?.plugins ?? []).filter(
    (p) =>
      !query ||
      p.name.toLowerCase().includes(query) ||
      p.description?.toLowerCase().includes(query) ||
      p.id.toLowerCase().includes(query)
  );

  const filteredUninstalled = uninstalledRegistry.filter(
    (e) =>
      !query ||
      e.name.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query) ||
      e.id.toLowerCase().includes(query)
  );

  // Group uninstalled registry entries by category (for Marketplace tab)
  const groupedUninstalled = filteredUninstalled.reduce((acc, entry) => {
    const category = entry.category || "utility";
    if (!acc[category]) acc[category] = [];
    acc[category].push(entry);
    return acc;
  }, {} as Record<string, RegistryEntry[]>);

  const marketplaceCategories = Object.keys(groupedUninstalled).sort(
    (a, b) => (CATEGORY_LABELS[a] || a).localeCompare(CATEGORY_LABELS[b] || b)
  );

  const availableCount = uninstalledRegistry.length;

  // Sorted flat list for marketplace list view
  const sortedUninstalled = [...filteredUninstalled].sort((a, b) => {
    let valA = "";
    let valB = "";
    if (marketplaceSort.key === "name") { valA = a.name; valB = b.name; }
    else if (marketplaceSort.key === "category") { valA = CATEGORY_LABELS[a.category || "utility"] || a.category || ""; valB = CATEGORY_LABELS[b.category || "utility"] || b.category || ""; }
    else if (marketplaceSort.key === "author") { valA = a.author || ""; valB = b.author || ""; }
    return marketplaceSort.dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
  });

  const handleMarketplaceSort = (key: "name" | "category" | "author") => {
    setMarketplaceSort(prev =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" }
    );
  };

  const handleInstalledSort = (key: "name" | "category" | "status") => {
    setInstalledSort(prev =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" }
    );
  };

  const sortedInstalled = [...filteredInstalled].sort((a, b) => {
    let valA = "";
    let valB = "";
    if (installedSort.key === "name") { valA = a.name; valB = b.name; }
    else if (installedSort.key === "category") {
      valA = CATEGORY_LABELS[a.category || "utility"] || a.category || "";
      valB = CATEGORY_LABELS[b.category || "utility"] || b.category || "";
    } else if (installedSort.key === "status") {
      const statusRank = (p: PluginInfo) => !p.enabled ? 2 : p.configured ? 0 : 1;
      return installedSort.dir === "asc"
        ? statusRank(a) - statusRank(b)
        : statusRank(b) - statusRank(a);
    }
    return installedSort.dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
  });

  const updatesAvailableCount = (data?.plugins ?? []).filter((p) => p.update_available === true).length;

  // Git install dialog (shared, used in Marketplace tab)
  const gitInstallDialog = (
    <Dialog open={gitDialogOpen} onOpenChange={setGitDialogOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Install Plugin from Git</DialogTitle>
          <DialogDescription>
            Install a plugin from any public git repository. The repository should contain a valid FiestaBoard plugin with a manifest.json.
          </DialogDescription>
        </DialogHeader>
        <Alert className="border-yellow-600 text-yellow-700 [&>svg]:text-yellow-600 dark:border-yellow-500 dark:text-yellow-400 dark:[&>svg]:text-yellow-500">
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle>Security Warning</AlertTitle>
          <AlertDescription>
            Only install plugins from sources you trust. External code runs on your device — review the repository before installing.
          </AlertDescription>
        </Alert>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="git-url">Repository URL</Label>
            <Input
              id="git-url"
              placeholder="https://github.com/user/fiestaboard-plugin-example.git"
              value={gitUrl}
              onChange={(e) => setGitUrl(e.target.value)}
              disabled={isInstallingGit}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="git-plugin-id">Plugin ID (optional)</Label>
              <Input
                id="git-plugin-id"
                placeholder="Auto-detected"
                value={gitPluginId}
                onChange={(e) => setGitPluginId(e.target.value)}
                disabled={isInstallingGit}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="git-branch">Branch (optional)</Label>
              <Input
                id="git-branch"
                placeholder="Default branch"
                value={gitBranch}
                onChange={(e) => setGitBranch(e.target.value)}
                disabled={isInstallingGit}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setGitDialogOpen(false)} disabled={isInstallingGit}>
            Cancel
          </Button>
          <Button onClick={handleInstallFromGit} disabled={isInstallingGit || !gitUrl.trim()}>
            {isInstallingGit ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Installing...
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                Install Plugin
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return (
    <PageLayout>
      <PageHeader
        icon={Puzzle}
        title="Integrations"
        description="Enable and configure data source plugins for your FiestaBoard"
      />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div
          className={
            activeTab === "marketplace"
              ? "mb-4 grid grid-cols-1 gap-3 items-center md:grid-cols-[auto_minmax(12rem,1fr)_auto]"
              : "mb-4 grid grid-cols-1 gap-3 items-center sm:grid-cols-[auto_minmax(0,1fr)]"
          }
        >
          <TabsList className="w-fit">
            <TabsTrigger value="installed">
              Installed
              {data && (
                <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 py-0 h-4">
                  {data.total}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="marketplace">
              Marketplace
              {availableCount > 0 && (
                <Badge variant="outline" className="ml-1.5 text-[10px] px-1.5 py-0 h-4">
                  {availableCount}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>
          <div className="relative min-w-0 w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder={activeTab === "installed" ? "Search installed plugins..." : "Search available plugins..."}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 w-full"
            />
          </div>
          {activeTab === "marketplace" && (
            <div className="flex items-center gap-2 shrink-0 md:justify-self-end">
              <div className="flex rounded-md border overflow-hidden">
                <Button
                  variant={marketplaceView === "card" ? "secondary" : "ghost"}
                  size="icon"
                  className="h-9 w-9 rounded-none border-0"
                  onClick={() => setMarketplaceView("card")}
                  aria-label="Card view"
                >
                  <LayoutGrid className="h-4 w-4" />
                </Button>
                <Button
                  variant={marketplaceView === "list" ? "secondary" : "ghost"}
                  size="icon"
                  className="h-9 w-9 rounded-none border-0"
                  onClick={() => setMarketplaceView("list")}
                  aria-label="List view"
                >
                  <LayoutList className="h-4 w-4" />
                </Button>
              </div>
              <Button variant="outline" className="gap-2" onClick={() => setGitDialogOpen(true)}>
                <GitBranch className="h-4 w-4" />
                Add from Git
              </Button>
            </div>
          )}
        </div>

        {/* ── Installed Tab ── */}
        <TabsContent value="installed" className="mt-0">
          {isLoading ? (
            <Card className="overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    <th className="px-4 py-2.5 text-left font-medium text-muted-foreground text-xs">Name</th>
                    <th className="px-4 py-2.5 text-left font-medium text-muted-foreground text-xs hidden sm:table-cell">Category</th>
                    <th className="px-4 py-2.5 text-left font-medium text-muted-foreground text-xs hidden md:table-cell">Status</th>
                    <th className="px-4 py-2.5 w-32" />
                  </tr>
                </thead>
                <tbody>
                  {[...Array(5)].map((_, i) => (
                    <tr key={i} className="border-b last:border-b-0">
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-3">
                          <Skeleton className="h-7 w-7 rounded-md shrink-0" />
                          <div className="flex items-center gap-2">
                            <Skeleton className="h-4 w-32" />
                            <Skeleton className="h-4 w-10" />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 hidden sm:table-cell">
                        <Skeleton className="h-4 w-20" />
                      </td>
                      <td className="px-4 py-2.5 hidden md:table-cell">
                        <Skeleton className="h-5 w-24 rounded-full" />
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end gap-1">
                          <Skeleton className="h-5 w-9 rounded-full" />
                          <Skeleton className="h-7 w-7 rounded" />
                          <Skeleton className="h-7 w-7 rounded" />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ) : error ? (
            <Card className="border-destructive">
              <CardContent className="flex items-center gap-3 py-6">
                <AlertCircle className="h-5 w-5 text-destructive" />
                <p className="text-sm text-destructive">
                  Failed to load plugins: {error instanceof Error ? error.message : "Unknown error"}
                </p>
              </CardContent>
            </Card>
          ) : filteredInstalled.length === 0 ? (
            <div className="text-center py-16">
              {query ? (
                <>
                  <Search className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground">No installed plugins match &quot;{searchQuery}&quot;</p>
                </>
              ) : (
                <>
                  <Puzzle className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="font-medium mb-1">No plugins installed yet</p>
                  <p className="text-sm text-muted-foreground mb-4">
                    Head to the Marketplace tab to discover and install plugins.
                  </p>
                  <Button variant="outline" onClick={() => setActiveTab("marketplace")}>
                    Browse Marketplace
                  </Button>
                </>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {updatesAvailableCount > 0 && (
                <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 dark:border-amber-800 dark:bg-amber-950/40">
                  <p className="text-sm text-amber-700 dark:text-amber-400">
                    {updatesAvailableCount} plugin update{updatesAvailableCount !== 1 ? "s" : ""} available
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 border-amber-300 text-amber-700 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900"
                    onClick={handleUpdateAll}
                    disabled={isUpdatingAll || !!updatingId}
                  >
                    <RefreshCw className={cn("h-3.5 w-3.5 mr-1.5", isUpdatingAll && "animate-spin")} />
                    {isUpdatingAll ? "Updating…" : `Update All (${updatesAvailableCount})`}
                  </Button>
                </div>
              )}
            <Card className="overflow-hidden animate-card-fade-in">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    {(["name", "category", "status"] as const).map((col) => {
                      const labels = { name: "Name", category: "Category", status: "Status" };
                      const active = installedSort.key === col;
                      return (
                        <th
                          key={col}
                          className={cn(
                            "px-4 py-2.5 text-left font-medium text-muted-foreground text-xs cursor-pointer select-none hover:text-foreground transition-colors",
                            col === "category" && "hidden sm:table-cell",
                            col === "status" && "hidden md:table-cell",
                          )}
                          onClick={() => handleInstalledSort(col)}
                        >
                          <span className="flex items-center gap-1">
                            {labels[col]}
                            {active ? (
                              installedSort.dir === "asc"
                                ? <ChevronUp className="h-3 w-3" />
                                : <ChevronDown className="h-3 w-3" />
                            ) : (
                              <ChevronsUp className="h-3 w-3 opacity-30" />
                            )}
                          </span>
                        </th>
                      );
                    })}
                    <th className="px-4 py-2.5 w-32" />
                  </tr>
                </thead>
                <tbody>
                  {sortedInstalled.map((plugin) => (
                    <PluginCard
                      key={plugin.id}
                      plugin={plugin}
                      onToggle={handleToggle}
                      isToggling={toggleMutation.isPending}
                      onConfigUpdate={() => queryClient.invalidateQueries({ queryKey: ["plugins"] })}
                      onUninstall={handleUninstall}
                      onUpdate={handleUpdate}
                      isUninstalling={uninstallingId === plugin.id}
                      isUpdating={updatingId === plugin.id}
                    />
                  ))}
                </tbody>
              </table>
            </Card>
            </div>
          )}
        </TabsContent>

        {/* ── Marketplace Tab ── */}
        <TabsContent value="marketplace" className="mt-0">
          {filteredUninstalled.length === 0 ? (
            <div className="text-center py-16">
              {query ? (
                <>
                  <Search className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground">No available plugins match &quot;{searchQuery}&quot;</p>
                </>
              ) : (
                <>
                  <CheckCircle className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="font-medium mb-1">All registry plugins are installed</p>
                  <p className="text-sm text-muted-foreground">
                    You can still install custom plugins from any public git repository.
                  </p>
                </>
              )}
            </div>
          ) : marketplaceView === "card" ? (
            <div className="space-y-6 animate-card-fade-in">
              {(() => {
                let globalIndex = 0;
                return marketplaceCategories.map((category) => {
                  const entries = groupedUninstalled[category] ?? [];
                  if (entries.length === 0) return null;
                  return (
                    <section key={category}>
                      <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-3 flex items-center gap-2">
                        {CATEGORY_LABELS[category] || category}
                        <span className="text-xs font-normal normal-case tracking-normal">
                          ({entries.length})
                        </span>
                      </h2>
                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 items-stretch">
                        {entries.map((entry) => {
                          const cardIndex = globalIndex++;
                          return (
                            <RegistryPluginCard
                              key={entry.id}
                              entry={entry}
                              onInstall={handleInstall}
                              isInstalling={installingId === entry.id}
                              index={cardIndex}
                            />
                          );
                        })}
                      </div>
                    </section>
                  );
                });
              })()}
            </div>
          ) : (
            /* List view */
            <Card className="overflow-hidden animate-card-fade-in">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    {(["name", "category", "author"] as const).map((col) => {
                      const labels = { name: "Name", category: "Category", author: "Author" };
                      const active = marketplaceSort.key === col;
                      return (
                        <th
                          key={col}
                          className="px-4 py-2.5 text-left font-medium text-muted-foreground text-xs cursor-pointer select-none hover:text-foreground transition-colors"
                          onClick={() => handleMarketplaceSort(col)}
                        >
                          <span className="flex items-center gap-1">
                            {labels[col]}
                            {active ? (
                              marketplaceSort.dir === "asc"
                                ? <ChevronUp className="h-3 w-3" />
                                : <ChevronDown className="h-3 w-3" />
                            ) : (
                              <ChevronsUp className="h-3 w-3 opacity-30" />
                            )}
                          </span>
                        </th>
                      );
                    })}
                    <th className="px-4 py-2.5 w-24" />
                  </tr>
                </thead>
                <tbody>
                  {sortedUninstalled.map((entry) => (
                    <RegistryPluginRow
                      key={entry.id}
                      entry={entry}
                      onInstall={handleInstall}
                      isInstalling={installingId === entry.id}
                    />
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {gitInstallDialog}
    </PageLayout>
  );
}

